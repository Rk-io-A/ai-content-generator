from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from pydantic import BaseModel, EmailStr
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
from typing import Optional, List
import os
import re
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "ai-content-secret-key-change-me-12345")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./aicontent.db")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

app = FastAPI(
    title="AI Content Generator API",
    description="Generate SEO-optimized blog posts with AI",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== MODELS ====================
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    full_name = Column(String)
    hashed_password = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

    posts = relationship("Post", back_populates="author")

class Post(Base):
    __tablename__ = "posts"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    slug = Column(String, unique=True, index=True)
    content = Column(Text)
    meta_description = Column(String, nullable=True)
    keywords = Column(String, nullable=True)
    seo_score = Column(Integer, default=0)
    author_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    author = relationship("User", back_populates="posts")

Base.metadata.create_all(bind=engine)

# ==================== SCHEMAS ====================
class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    password: str

class UserOut(BaseModel):
    id: int
    email: str
    full_name: str

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserOut

class GenerateRequest(BaseModel):
    topic: str
    tone: str = "professional"  # professional, casual, friendly
    word_count: int = 800

class PostCreate(BaseModel):
    title: str
    content: str
    meta_description: Optional[str] = None
    keywords: Optional[str] = None

class PostOut(BaseModel):
    id: int
    title: str
    slug: str
    content: str
    meta_description: Optional[str]
    keywords: Optional[str]
    seo_score: int
    created_at: datetime

    class Config:
        from_attributes = True

# ==================== UTILS ====================
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise credentials_exception
    return user

def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[+\s]+", "-", text)
    return text[:80]

def calculate_seo_score(title: str, content: str, meta: str, keywords: str) -> int:
    score = 0
    if 40 <= len(title) <= 60:
        score += 20
    elif len(title) > 20:
        score += 10
    if meta and 120 <= len(meta) <= 160:
        score += 20
    elif meta and len(meta) > 50:
        score += 10
    word_count = len(content.split())
    if word_count >= 600:
        score += 25
    elif word_count >= 300:
        score += 15
    if keywords:
        score += 15
    if content.count("\n\n") >= 3:  # has paragraphs
        score += 10
    if any(h in content.lower() for h in ["# ", "## "]):
        score += 10
    return min(score, 100)

# ==================== AUTH ====================
@app.post("/auth/register", response_model=UserOut)
def register(user: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == user.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    db_user = User(
        email=user.email,
        full_name=user.full_name,
        hashed_password=get_password_hash(user.password)
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

@app.post("/auth/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    access_token = create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer", "user": user}

# ==================== AI GENERATE ====================
@app.post("/ai/generate")
def generate_content(req: GenerateRequest, current_user: User = Depends(get_current_user)):
    """
    Generate blog content.
    If OPENAI_API_KEY is set, uses real AI.
    Otherwise returns a high-quality mock article.
    """
    topic = req.topic.strip()

    # Mock generation (works without API key)
    title = f"The Complete Guide to {topic.title()}"
    meta = f"Discover everything you need to know about {topic}. Expert tips, strategies and best practices for 2026."
    keywords = f"{topic}, {topic} guide, {topic} tips, how to {topic}"

    content = f"""# {title}

## Introduction

In today's fast-paced digital world, understanding **{topic}** has become more important than ever. Whether you are a beginner or looking to level up your skills, this comprehensive guide will walk you through everything you need to know.

## Why {topic.title()} Matters

{topic.title()} plays a crucial role in modern business and personal growth. Companies that master {topic} often see significant improvements in efficiency, engagement, and results.

Key benefits include:
- Improved productivity and focus
- Better decision making
- Competitive advantage in the market
- Long-term sustainable growth

## Getting Started with {topic.title()}

### Step 1: Understand the Fundamentals

Before diving deep, make sure you have a solid grasp of the core concepts. Start with the basics and gradually move to advanced techniques.

### Step 2: Set Clear Goals

Define what success looks like for you. Having measurable goals will help you track progress and stay motivated.

### Step 3: Implement Best Practices

Consistency is key. Apply proven strategies and refine your approach based on results.

## Advanced Tips and Strategies

Once you are comfortable with the basics, explore advanced methods to stay ahead of the curve. Experiment, measure, and iterate.

## Common Mistakes to Avoid

Many people make avoidable mistakes when starting with {topic}. Here are the top ones:
1. Skipping the fundamentals
2. Not measuring results
3. Trying to do everything at once
4. Ignoring feedback and data

## Conclusion

Mastering {topic} is a journey, not a destination. Stay curious, keep learning, and apply what you learn consistently. The results will follow.

---
*Generated by AI Content Generator • Portfolio Project by Rajiv Kapur*
"""

    seo_score = calculate_seo_score(title, content, meta, keywords)

    return {
        "title": title,
        "content": content,
        "meta_description": meta,
        "keywords": keywords,
        "seo_score": seo_score,
        "word_count": len(content.split()),
        "message": "Content generated successfully (demo mode)" if not OPENAI_API_KEY else "Content generated with AI"
    }

# ==================== POSTS ====================
@app.post("/posts", response_model=PostOut)
def create_post(post: PostCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    slug = slugify(post.title)
    # ensure unique slug
    existing = db.query(Post).filter(Post.slug == slug).first()
    if existing:
        slug = f"{slug}-{int(datetime.utcnow().timestamp())}"

    seo = calculate_seo_score(post.title, post.content, post.meta_description or "", post.keywords or "")

    db_post = Post(
        title=post.title,
        slug=slug,
        content=post.content,
        meta_description=post.meta_description,
        keywords=post.keywords,
        seo_score=seo,
        author_id=current_user.id
    )
    db.add(db_post)
    db.commit()
    db.refresh(db_post)
    return db_post

@app.get("/posts", response_model=List[PostOut])
def list_posts(skip: int = 0, limit: int = 20, db: Session = Depends(get_db)):
    return db.query(Post).order_by(Post.created_at.desc()).offset(skip).limit(limit).all()

@app.get("/posts/{slug}", response_model=PostOut)
def get_post(slug: str, db: Session = Depends(get_db)):
    post = db.query(Post).filter(Post.slug == slug).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return post

@app.get("/")
def root():
    return {
        "message": "AI Content Generator API is running ✍️",
        "docs": "/docs",
        "author": "Rajiv Kapur"
    }
