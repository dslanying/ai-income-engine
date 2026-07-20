from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./microsaas.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)

    # Subscription fields (Lemon Squeezy)
    plan = Column(String, default="free")  # free, creator, pro
    lemonsqueezy_customer_id = Column(String, nullable=True)
    lemonsqueezy_subscription_id = Column(String, nullable=True)
    lemonsqueezy_order_id = Column(String, nullable=True)
    subscription_status = Column(String, default="inactive")  # active, canceled, expired, on_trial, paused
    subscription_end_date = Column(DateTime, nullable=True)
    articles_generated_this_month = Column(Integer, default=0)
    articles_monthly_reset = Column(DateTime, default=datetime.utcnow)

    articles = relationship("Article", back_populates="owner", cascade="all, delete-orphan")


class Article(Base):
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    keyword = Column(String, nullable=False)
    title = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    meta_description = Column(String, nullable=True)
    tags = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    word_count = Column(Integer, default=0)

    owner = relationship("User", back_populates="articles")


# Create tables
Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
