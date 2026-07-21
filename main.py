"""
AI Income Engine - MicroSaaS Application
Payment integration: Lemon Squeezy (replaced Stripe)

============================================================
Lemon Squeezy Configuration Steps
============================================================

1. Register a Lemon Squeezy account
   Go to https://www.lemonsqueezy.com and sign up.

2. Create a Store
   In your Lemon Squeezy Dashboard, create a new Store.
   Copy the Store ID (e.g., 12345) and set it as LEMONSQUEEZY_STORE_ID.

3. Create Products & Variants
   Create the following 3 Products in your Store:

   Product 1: "Starter" (Free plan - no product needed in Lemon Squeezy)
     - This is the default free plan, handled entirely in-app.

   Product 2: "Creator" ($12/month)
     - Create a Product named "Creator Plan"
     - Add a Variant with recurring billing: $12/month
     - Copy the Variant ID (e.g., 67890) and set as LEMONSQUEEZY_VARIANT_ID_CREATOR

   Product 3: "Pro" ($29/month)
     - Create a Product named "Pro Plan"
     - Add a Variant with recurring billing: $29/month
     - Copy the Variant ID (e.g., 11111) and set as LEMONSQUEEZY_VARIANT_ID_PRO

4. Get your API Key
   Go to Settings > API Keys in Lemon Squeezy Dashboard.
   Generate a new API key (format: "lsq_sk_xxxxx" or "lsq_live_xxxxx").
   Set it as LEMONSQUEEZY_API_KEY.

5. Configure Webhook URL
   In Lemon Squeezy Dashboard, go to Settings > Webhooks.
   Add a new webhook pointing to: https://yourdomain.com/webhook
   Subscribe to the following events:
     - subscription_created
     - subscription_updated
     - subscription_cancelled
     - subscription_expired
     - order_created

6. Set Environment Variables
   Copy .env.example to .env and fill in all values.
   Make sure LEMONSQUEEZY_API_KEY, LEMONSQUEEZY_STORE_ID, and
   LEMONSQUEEZY_VARIANT_ID_CREATOR / LEMONSQUEEZY_VARIANT_ID_PRO are set.

============================================================
"""

import os
import uuid
import json
import hashlib
import hmac
import httpx
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import FastAPI, Request, Response, Form, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from dotenv import load_dotenv

from models import get_db, User, Article, SessionLocal

load_dotenv()

# App Config
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-me")
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
APP_URL = os.getenv("APP_URL", "http://localhost:8000")

# Lemon Squeezy Config
LEMONSQUEEZY_API_KEY = os.getenv("LEMONSQUEEZY_API_KEY", "")
LEMONSQUEEZY_STORE_ID = os.getenv("LEMONSQUEEZY_STORE_ID", "")
LEMONSQUEEZY_WEBHOOK_SECRET = os.getenv("LEMONSQUEEZY_WEBHOOK_SECRET", "")
LEMONSQUEEZY_VARIANT_ID_CREATOR = os.getenv("LEMONSQUEEZY_VARIANT_ID_CREATOR", "")
LEMONSQUEEZY_VARIANT_ID_PRO = os.getenv("LEMONSQUEEZY_VARIANT_ID_PRO", "")

# Lemon Squeezy API client
LEMONSQUEEZY_API_BASE = "https://api.lemonsqueezy.com/v1"


def lemonsqueezy_headers():
    """Return headers for Lemon Squeezy API requests."""
    return {
        "Authorization": f"Bearer {LEMONSQUEEZY_API_KEY}",
        "Accept": "application/vnd.api+json",
        "Content-Type": "application/vnd.api+json",
    }


async def lemonsqueezy_post(endpoint: str, data: dict) -> dict:
    """Make a POST request to the Lemon Squeezy API."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{LEMONSQUEEZY_API_BASE}{endpoint}",
            headers=lemonsqueezy_headers(),
            json=data,
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()


async def lemonsqueezy_get(endpoint: str) -> dict:
    """Make a GET request to the Lemon Squeezy API."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{LEMONSQUEEZY_API_BASE}{endpoint}",
            headers=lemonsqueezy_headers(),
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()


async def lemonsqueezy_delete(endpoint: str) -> dict:
    """Make a DELETE request to the Lemon Squeezy API."""
    async with httpx.AsyncClient() as client:
        response = await client.delete(
            f"{LEMONSQUEEZY_API_BASE}{endpoint}",
            headers=lemonsqueezy_headers(),
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()


# Plans config
PLANS = {
    "free": {
        "name": "Starter",
        "price": 0,
        "articles_per_month": 5,
        "features": ["5 generations/month", "Blog posts & product descriptions", "Basic formatting & meta tags", "Standard support"]
    },
    "creator": {
        "name": "Creator",
        "price": 12,
        "articles_per_month": 50,
        "features": ["50 generations/month", "YouTube scripts & social media posts", "Email marketing sequences", "Affiliate marketing content", "Export to HTML/Markdown"]
    },
    "pro": {
        "name": "Pro",
        "price": 29,
        "articles_per_month": 999999,
        "features": ["Unlimited generations", "All content types included", "API access", "Priority support", "White-label exports"]
    }
}

app = FastAPI(title="AI Income Engine", version="2.1.0")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, max_age=3600 * 24 * 7)
import os
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
_env = Environment(
    loader=FileSystemLoader(os.path.join(os.path.dirname(__file__), "templates")),
    autoescape=True,
    cache_size=0,
)
# Custom template render to bypass Starlette Jinja2Templates bug
def render_template(request: Request, template_name: str, status_code: int = 200, **context):
    """Render a Jinja2 template with the given context and return HTMLResponse."""
    context["request"] = request
    template = _env.get_template(template_name)
    html = template.render(**context)
    return HTMLResponse(content=html, status_code=status_code)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ===================== Helpers =====================

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    user = db.query(User).filter(User.id == user_id).first()
    return user

def require_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=status.HTTP_302_FOUND, detail="Not authenticated")
    return user

def require_admin(request: Request, db: Session = Depends(get_db)) -> User:
    user = require_user(request, db)
    if user.email != os.getenv("ADMIN_EMAIL", "admin@example.com"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

def reset_monthly_counter_if_needed(user: User):
    now = datetime.utcnow()
    if user.articles_monthly_reset is None or user.articles_monthly_reset.month != now.month or user.articles_monthly_reset.year != now.year:
        user.articles_generated_this_month = 0
        user.articles_monthly_reset = now

def can_generate_article(user: User) -> bool:
    reset_monthly_counter_if_needed(user)
    plan = PLANS.get(user.plan, PLANS["free"])
    return user.articles_generated_this_month < plan["articles_per_month"]


# ===================== AI Content Generator =====================

class AIContentGenerator:
    # Blog post templates
    BLOG_TEMPLATES = {
        "introduction": [
            """In today's digital landscape, {keyword} has become more important than ever. Whether you're a beginner or an experienced professional, understanding the nuances of {keyword} can significantly impact your success.""",
            """Are you looking to master {keyword}? You've come to the right place. This comprehensive guide will walk you through everything you need to know about {keyword} and how to leverage it effectively.""",
            """{keyword} is transforming the way businesses operate online. In this article, we'll explore the key strategies, best practices, and actionable tips to help you stay ahead of the curve."""
        ],
        "section_1": [
            """## Understanding {keyword}

At its core, {keyword} represents a fundamental shift in how we approach digital strategy. By focusing on the key elements that drive results, you can create a solid foundation for long-term success.

### Key Components

- **Strategic Planning**: Developing a clear roadmap for your {keyword} initiatives
- **Implementation**: Executing your strategy with precision and attention to detail
- **Measurement**: Tracking key metrics to ensure you're on the right path
- **Optimization**: Continuously refining your approach based on data-driven insights""",
            """## What is {keyword}?

{keyword} encompasses a wide range of practices and methodologies designed to improve your online presence. From technical foundations to creative execution, every aspect plays a crucial role in achieving your goals.

### The Fundamentals

1. Research and analysis of market trends
2. Development of targeted strategies
3. Content creation and distribution
4. Performance monitoring and reporting"""
        ],
        "section_2": [
            """## Why {keyword} Matters

The importance of {keyword} cannot be overstated. Organizations that invest in {keyword} consistently outperform their competitors across key performance indicators.

### Benefits of {keyword}

| Benefit | Impact | Timeframe |
|---------|--------|-----------|
| Increased visibility | High | 1-3 months |
| Better engagement | Medium | 2-4 months |
| Higher conversions | High | 3-6 months |
| Sustainable growth | Very High | 6+ months |

By prioritizing {keyword} in your strategy, you position your business for sustainable growth and long-term success.""",
            """## The Benefits of Implementing {keyword}

Implementing {keyword} in your workflow delivers measurable results that directly impact your bottom line. Let's explore the key advantages:

- **Cost Efficiency**: Reduce wasted spend by targeting the right audience
- **Scalability**: Grow your efforts without proportionally increasing resources
- **Competitive Advantage**: Stay ahead of competitors who neglect {keyword}
- **User Satisfaction**: Deliver better experiences that keep customers coming back"""
        ],
        "section_3": [
            """## Best Practices for {keyword}

To maximize the impact of your {keyword} efforts, follow these proven best practices:

### 1. Start with Clear Objectives
Define what success looks like for your {keyword} initiatives. Establish specific, measurable goals that align with your broader business objectives.

### 2. Focus on Quality Over Quantity
When it comes to {keyword}, quality always wins. Invest time and resources in creating high-value outputs rather than chasing volume.

### 3. Stay Updated with Trends
The world of {keyword} evolves rapidly. Make continuous learning a priority and adapt your strategies as the landscape changes.

### 4. Leverage the Right Tools
Utilize specialized tools and platforms designed to streamline your {keyword} workflow and provide actionable insights.""",
            """## {keyword} Best Practices in 2026

Follow these expert-recommended practices to get the most out of your {keyword} strategy:

> "Success in {keyword} comes from consistent execution and willingness to adapt based on data." — Industry Expert

1. **Audit Your Current Approach**: Identify gaps and opportunities in your existing {keyword} strategy
2. **Set Realistic Milestones**: Break down your goals into achievable quarterly targets
3. **Invest in Training**: Ensure your team has the skills needed to execute effectively
4. **Monitor Competitors**: Keep an eye on what others in your space are doing with {keyword}"""
        ],
        "conclusion": [
            """## Conclusion

{keyword} is not just a trend — it's a critical component of modern digital strategy. By following the guidelines and best practices outlined in this article, you can build a robust {keyword} strategy that delivers real results.

Remember: the key to success is consistency. Start implementing these strategies today, measure your progress, and continuously optimize your approach. The investment you make in {keyword} today will pay dividends for years to come.

---

*Ready to take your {keyword} strategy to the next level? Sign up for our Pro plan and unlock unlimited content generation with all content types included.*""",
            """## Final Thoughts

Mastering {keyword} takes time, but the rewards are well worth the effort. As you've learned in this guide, a strategic approach to {keyword} can transform your online presence and drive meaningful business results.

### Next Steps

1. Review your current {keyword} strategy against the best practices discussed
2. Identify quick wins you can implement immediately
3. Develop a 90-day action plan for {keyword} improvement
4. Consider upgrading your tools and resources for better efficiency

Thank you for reading! If you found this guide helpful, share it with your network and subscribe for more expert insights on {keyword}."""
        ]
    }

    # YouTube script templates
    YOUTUBE_TEMPLATES = {
        "intro": [
            """[HOOK] What if I told you that {keyword} could completely change the way you make money online? In this video, I'm going to break down exactly how you can start using {keyword} to generate income — even if you're a complete beginner.

[TIMESTAMP: 0:00]""",
            """[HOOK] Stop scrolling! If you want to learn about {keyword} and actually start earning from it, this is the only video you need to watch today. I've spent months researching this, and I'm sharing everything for free.

[TIMESTAMP: 0:00]"""
        ],
        "body": [
            """[SECTION 1: What is {keyword}?]
Let me explain this in the simplest way possible. {keyword} is essentially [definition]. Here's why it matters for anyone looking to make money online:

- It's a growing market with huge demand
- Low barrier to entry for beginners
- Scalable — you can grow as much as you want
- Multiple income streams from a single skill

[SECTION 2: How to Get Started]
Step 1: The first thing you need to do is understand the basics. Start by researching [subtopic].
Step 2: Set up your foundation. This means [actionable step].
Step 3: Create your first piece of content around {keyword}.
Step 4: Publish and promote across platforms.

[SECTION 3: Common Mistakes to Avoid]
- Don't try to do everything at once
- Don't skip the research phase
- Don't ignore analytics and feedback
- Don't give up after the first week""",
            """[SECTION 1: Why {keyword} is the Hottest Trend Right Now]
Let me start by sharing some numbers. The {keyword} industry has grown by [stat]% in the last year alone. And the best part? Most people still have no idea about this opportunity.

Here are 3 reasons why {keyword} is blowing up:
1. Companies are desperate for people who understand this
2. The tools are now accessible to everyone
3. You can start with zero upfront investment

[SECTION 2: My Step-by-Step Strategy]
Here's exactly how I would start with {keyword} today:
- First, pick a specific niche within {keyword}
- Then, create content consistently for 30 days
- Build an audience on at least 2 platforms
- Monetize through [method 1], [method 2], or [method 3]

[SECTION 3: Realistic Income Expectations]
Let's talk money. In your first month, you could realistically earn $200-$500. By month 3, with consistent effort, $1,000-$2,000 is very achievable. And by month 6? Some people are pulling in $5,000+ per month."""
        ],
        "outro": [
            """[OUTRO]
And that's everything you need to know about {keyword} to start making money online. If you found this video helpful, smash that like button and subscribe for more content like this.

Drop a comment below telling me which step you're going to take first. I read every single comment and I'll be there to help.

See you in the next video!

[END SCREEN: Subscribe + Related Video]""",
            """[OUTRO]
Thanks for watching! If you're serious about making money with {keyword}, bookmark this video and come back to it whenever you need a refresher.

Don't forget to hit subscribe and turn on notifications so you never miss a money-making opportunity.

Link in the description for the free resource I mentioned. Until next time!

[END SCREEN: Subscribe + Related Video]"""
        ]
    }

    # Social media post templates
    SOCIAL_TEMPLATES = {
        "twitter": [
            """{keyword} is the ultimate money-making hack most people sleep on.

Here's why you should start TODAY:

1/ It's growing 3x faster than traditional methods
2/ You can start with $0 investment
3/ The earning potential is massive

Thread coming up with my exact step-by-step strategy.

#MakeMoneyOnline #PassiveIncome #SideHustle""",
            """I went from $0 to $3,000/month using {keyword}.

The secret? I stopped overthinking and started executing.

Here are the 5 things that actually moved the needle for me:

A thread on {keyword}:

#OnlineBusiness #AI #MoneyTips"""
        ],
        "linkedin": [
            """I spent 6 months studying {keyword}.

What I discovered surprised me:

Most people approach it completely wrong.

Here's what actually works in 2026:

1. Start with a specific, targeted niche
2. Create content that solves real problems
3. Build relationships, not just followers
4. Diversify your income streams early
5. Track everything and double down on what works

The people making real money with {keyword} aren't the loudest — they're the most consistent.

If you're thinking about getting started, my biggest advice: begin today, not tomorrow.

What's your experience with {keyword}? I'd love to hear your story in the comments.

#{keyword} #ContentCreation #OnlineIncome""",
            """{keyword} changed my career trajectory.

18 months ago, I was working 9-to-5 and feeling stuck.

Today, I earn more from {keyword} than my full-time job ever paid.

The turning point? I stopped treating it like a hobby and started treating it like a business.

3 mindset shifts that made all the difference:

1. Think long-term, act daily
2. Invest in learning before earning
3. Quality content > quantity every time

The opportunity in {keyword} right now is massive. But it won't wait forever.

Start now. Learn fast. Iterate constantly.

Who else is building something with {keyword}? Let's connect in the comments.

#Entrepreneurship #AI #DigitalEconomy"""
        ]
    }

    # Product description templates
    PRODUCT_DESC_TEMPLATES = {
        "amazon": [
            """{keyword} - The Ultimate Solution You've Been Looking For

Are you tired of settling for mediocre products? Introducing our premium {keyword} — designed for people who demand the best.

**Key Features:**
- High-quality materials built to last
- User-friendly design — perfect for beginners and pros alike
- Backed by our 100% satisfaction guarantee
- Fast shipping — get it delivered to your door in 2-3 days

**Why Choose Us?**
With thousands of satisfied customers and an average rating of 4.8 stars, our {keyword} stands out from the competition. We've spent years perfecting every detail so you don't have to compromise.

**Package Includes:**
- 1x Premium {keyword}
- Quick-start guide
- Lifetime warranty card

Don't wait — order now and see the difference for yourself! Add to cart today.

---
*100% Money-Back Guarantee | Free 30-Day Returns | 24/7 Customer Support*""",
            """Premium {keyword} — Engineered for Excellence

Discover why over 10,000+ customers have made the switch to our {keyword}. Whether you're a first-time buyer or upgrading, this product delivers unmatched value.

**Product Highlights:**
- Advanced technology for superior performance
- Sleek, modern design that looks great anywhere
- Durable construction — built to withstand daily use
- Eco-friendly materials — good for you and the planet

**What Customers Are Saying:**
"Best {keyword} I've ever owned. Worth every penny." — Verified Purchase
"I've tried 5 different brands. This one blows them all away." — Verified Purchase

**Perfect For:**
- Home use
- Professional settings
- Gifts for friends and family

Order now and experience the difference quality makes.
---
*Prime Eligible | 2-Day Shipping | 1-Year Warranty*"""
        ],
        "etsy": [
            """Handcrafted {keyword} — Made with Love & Care

Each piece is carefully crafted by hand, ensuring unique character and exceptional quality that mass-produced items simply can't match.

**Details:**
- Material: Premium, sustainably sourced
- Dimensions: Customizable to your needs
- Processing time: 3-5 business days
- Shipping: Free standard shipping on all orders

**Why You'll Love It:**
- One-of-a-kind design — no two pieces are exactly alike
- Perfect gift for [occasion]
- Eco-conscious packaging
- Personalization available (add a note at checkout!)

**Care Instructions:**
Simple care to keep your {keyword} looking beautiful for years.

--- 
*Thank you for supporting small business! Every purchase helps an independent creator.*

**Message me** if you'd like a custom order or have any questions. I'd love to hear from you!"""
        ]
    }

    # Email marketing sequence templates
    EMAIL_TEMPLATES = {
        "sequence": [
            """Subject: How {keyword} Can Help You Earn $1,000+/Month Online

Hi {{first_name}},

Let me be real with you for a second.

The internet has created more wealth-building opportunities than any other time in human history. And {keyword} is one of the most underrated ways to cash in.

Here's what most people don't know:

- {keyword} is a growing market worth billions
- You don't need a degree or special skills to get started
- The barrier to entry is lower than ever in 2026

Over the next 5 days, I'm going to send you my complete blueprint for making money with {keyword}. No fluff — just actionable steps you can start implementing today.

Tomorrow, I'll show you Step 1: Finding your profitable niche.

Talk soon,

[Your Name]

P.S. If you want to fast-track your results, check out our AI Income Engine tool — it generates all the content you need in seconds: [Link]

---

Subject: Day 1 - Finding Your Profitable {keyword} Niche

Hi {{first_name}},

Welcome to Day 1 of our {keyword} masterclass!

Today, we're focusing on the most important decision you'll make: choosing your niche.

Here's the formula for a profitable niche:

1. **High demand** — People are actively searching for this
2. **Low competition** — Not everyone is doing this yet
3. **Monetization potential** — Multiple ways to earn

Some of the best {keyword} niches right now:
- [Niche 1]
- [Niche 2]
- [Niche 3]

Your action step for today: Pick ONE niche and commit to it for 30 days.

Tomorrow: Day 2 — Creating Your First Piece of Content

Best,
[Your Name]

---

Subject: Day 2 - Creating Your First {keyword} Content

Hi {{first_name}},

Great job picking your niche! Now let's create content.

Here's the simple 3-step framework I use:

1. Research: Find the top 10 questions people are asking about your topic
2. Create: Write a comprehensive answer to each question
3. Publish: Put it where your audience can find it

The secret sauce? Our AI Income Engine generates all of this for you in under 30 seconds. Enter your keyword, pick your content type, and you're done.

Try it free: [Link]

Tomorrow: Day 3 — Getting Your First 1,000 Views

Best,
[Your Name]"""
        ]
    }

    # Affiliate marketing content templates
    AFFILIATE_TEMPLATES = {
        "review": [
            """# {keyword} Review (2026) — Is It Worth Your Money?

**Disclosure:** This post contains affiliate links. If you purchase through them, I may earn a commission at no extra cost to you. I only recommend products I genuinely believe in.

## Quick Verdict: {keyword} Gets a Solid 4.5/5 Stars

After testing {keyword} extensively for the past 3 months, here's my honest take: **it's one of the best options on the market right now.**

## What I Loved

- **Ease of use** — Even a complete beginner can get started in under 10 minutes
- **Value for money** — Priced competitively compared to alternatives
- **Customer support** — Responsive and helpful
- **Results** — I noticed measurable improvements within the first week

## What Could Be Better

- The onboarding process could be more streamlined
- Advanced features have a slight learning curve

## Who Should Buy {keyword}?

- Beginners looking for an affordable entry point
- Intermediate users wanting to scale their results
- Anyone who values quality over the cheapest option

## Final Verdict

If you're serious about {keyword}, this is a solid investment. The ROI speaks for itself.

**[Get {keyword} Here — Special Discount Link]** *(affiliate link)

---

*Have questions? Drop them in the comments and I'll answer personally.*

*Tags: {keyword} review, {keyword} 2026, best {keyword}, {keyword} alternatives*"""
        ],
        "comparison": [
            """# {keyword}: Top 5 Options Compared (2026 Edition)

Trying to find the best {keyword}? I've done the research so you don't have to. Here are the top 5 options ranked from best to worst.

## 1. [Product A] — Best Overall
- Price: $$$
- Best for: Most users
- Rating: 4.7/5
- **[Check Price]** *(affiliate link)*

## 2. [Product B] — Best Value
- Price: $$
- Best for: Budget-conscious buyers
- Rating: 4.5/5
- **[Check Price]** *(affiliate link)*

## 3. [Product C] — Best for Beginners
- Price: $$
- Best for: Newbies
- Rating: 4.3/5
- **[Check Price]** *(affiliate link)*

## 4. [Product D] — Premium Pick
- Price: $$$$
- Best for: Professionals
- Rating: 4.6/5
- **[Check Price]** *(affiliate link)*

## 5. [Product E] — Budget Option
- Price: $
- Best for: Trying it out
- Rating: 3.9/5
- **[Check Price]** *(affiliate link)*

## My Recommendation

If you're just starting out, go with option #2 for the best value. If budget isn't a concern, option #1 delivers the best overall experience.

---

*Disclaimer: Some links above are affiliate links. I earn a small commission if you purchase, at no extra cost to you.*"""
        ]
    }

    @classmethod
    def generate(cls, keyword: str, content_type: str = "blog") -> dict:
        import random
        keyword_lower = keyword.lower()
        keyword_title = keyword.title()

        if content_type == "blog":
            parts = {
                "intro": random.choice(cls.BLOG_TEMPLATES["introduction"]).format(keyword=keyword_title),
                "s1": random.choice(cls.BLOG_TEMPLATES["section_1"]).format(keyword=keyword_title),
                "s2": random.choice(cls.BLOG_TEMPLATES["section_2"]).format(keyword=keyword_title),
                "s3": random.choice(cls.BLOG_TEMPLATES["section_3"]).format(keyword=keyword_title),
                "conclusion": random.choice(cls.BLOG_TEMPLATES["conclusion"]).format(keyword=keyword_title),
            }
            content = f"""# The Complete Guide to {keyword_title}\n\n{parts['intro']}\n\n{parts['s1']}\n\n{parts['s2']}\n\n{parts['s3']}\n\n{parts['conclusion']}\n"""
            title = f"The Ultimate Guide to {keyword_title}: Strategies, Tips & Best Practices for 2026"
            meta = f"Discover everything you need to know about {keyword_title}. Learn proven strategies, expert tips, and best practices to master {keyword_lower} and achieve your goals."
            tags = f"{keyword_lower}, guide, best practices, strategy, tips, 2026"

        elif content_type == "youtube":
            intro = random.choice(cls.YOUTUBE_TEMPLATES["intro"]).format(keyword=keyword_title)
            body = random.choice(cls.YOUTUBE_TEMPLATES["body"]).format(keyword=keyword_title)
            outro = random.choice(cls.YOUTUBE_TEMPLATES["outro"]).format(keyword=keyword_title)
            content = f"{intro}\n\n{body}\n\n{outro}\n"
            title = f"YouTube Script: How to Make Money with {keyword_title} (2026)"
            meta = f"Learn how to make money with {keyword_lower}. Complete YouTube script with hook, main content, and call-to-action."
            tags = f"{keyword_lower}, youtube script, make money online, side hustle, 2026"

        elif content_type == "twitter":
            content = random.choice(cls.SOCIAL_TEMPLATES["twitter"]).format(keyword=keyword_title)
            title = f"Twitter/X Thread: {keyword_title}"
            meta = f"Engaging Twitter thread about {keyword_lower} for online income."
            tags = f"{keyword_lower}, twitter, thread, social media, online income"

        elif content_type == "linkedin":
            content = random.choice(cls.SOCIAL_TEMPLATES["linkedin"]).format(keyword=keyword_title)
            title = f"LinkedIn Post: {keyword_title}"
            meta = f"Professional LinkedIn post about {keyword_lower} for career growth and income."
            tags = f"{keyword_lower}, linkedin, professional, networking, career"

        elif content_type == "amazon":
            content = random.choice(cls.PRODUCT_DESC_TEMPLATES["amazon"]).format(keyword=keyword_title)
            title = f"Amazon Product Listing: {keyword_title}"
            meta = f"Optimized Amazon product description for {keyword_lower}."
            tags = f"{keyword_lower}, amazon, product listing, ecommerce, 2026"

        elif content_type == "etsy":
            content = random.choice(cls.PRODUCT_DESC_TEMPLATES["etsy"]).format(keyword=keyword_title)
            title = f"Etsy Product Description: {keyword_title}"
            meta = f"Handcrafted Etsy product listing for {keyword_lower}."
            tags = f"{keyword_lower}, etsy, handmade, product description, craft"

        elif content_type == "email":
            content = random.choice(cls.EMAIL_TEMPLATES["sequence"]).format(keyword=keyword_title)
            title = f"Email Marketing Sequence: {keyword_title}"
            meta = f"Automated email marketing sequence for {keyword_lower} promotions."
            tags = f"{keyword_lower}, email marketing, automation, sequence, affiliate"

        elif content_type == "affiliate_review":
            content = random.choice(cls.AFFILIATE_TEMPLATES["review"]).format(keyword=keyword_title)
            title = f"Affiliate Review: {keyword_title} (2026)"
            meta = f"Honest review of {keyword_lower} with affiliate links and detailed analysis."
            tags = f"{keyword_lower}, review, affiliate, 2026, comparison"

        elif content_type == "affiliate_comparison":
            content = random.choice(cls.AFFILIATE_TEMPLATES["comparison"]).format(keyword=keyword_title)
            title = f"Affiliate Comparison: Top 5 {keyword_title} Products"
            meta = f"Comparison of the best {keyword_lower} products with affiliate links."
            tags = f"{keyword_lower}, comparison, affiliate, best products, 2026"

        else:
            # Default to blog
            return cls.generate(keyword, "blog")

        word_count = len(content.split())

        return {
            "title": title,
            "content": content,
            "meta_description": meta,
            "tags": tags,
            "word_count": word_count,
            "content_type": content_type
        }


# ===================== Routes =====================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    return render_template(request, "index.html", user=user, plans=PLANS)


@app.get("/pricing", response_class=HTMLResponse)
async def pricing(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    return render_template(request, "pricing.html", user=user, plans=PLANS)


# ---------------- Auth Routes ----------------

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = ""):
    return render_template(request, "login.html", error=error)


@app.post("/login")
async def login(
    request: Request,
    response: Response,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.hashed_password):
        return render_template(request, "login.html", error="Invalid email or password", status_code=401)

    request.session["user_id"] = user.id
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, error: str = ""):
    return render_template(request, "register.html", error=error)


@app.post("/register")
async def register(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    existing = db.query(User).filter((User.email == email) | (User.username == username)).first()
    if existing:
        return render_template(request, "register.html", error="Email or username already registered", status_code=400)

    user = User(
        email=email,
        username=username,
        hashed_password=hash_password(password)
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    request.session["user_id"] = user.id
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)


# ---------------- Dashboard & Generator ----------------

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    reset_monthly_counter_if_needed(user)
    db.commit()

    plan = PLANS.get(user.plan, PLANS["free"])
    articles_remaining = max(0, plan["articles_per_month"] - user.articles_generated_this_month)

    return render_template(request, "dashboard.html", user=user, plan=plan, articles_remaining=articles_remaining if user.plan == "free" else "Unlimited")


@app.get("/generate", response_class=HTMLResponse)
async def generate_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    if not can_generate_article(user):
        return RedirectResponse(url="/pricing?error=limit_reached", status_code=status.HTTP_302_FOUND)

    return render_template(request, "generate.html", user=user)


@app.post("/generate")
async def generate_article(
    request: Request,
    keyword: str = Form(...),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    if not can_generate_article(user):
        return RedirectResponse(url="/pricing?error=limit_reached", status_code=status.HTTP_302_FOUND)

    result = AIContentGenerator.generate(keyword)

    article = Article(
        user_id=user.id,
        keyword=keyword,
        title=result["title"],
        content=result["content"],
        meta_description=result["meta_description"],
        tags=result["tags"],
        word_count=result["word_count"]
    )
    db.add(article)
    user.articles_generated_this_month += 1
    db.commit()
    db.refresh(article)

    return RedirectResponse(url=f"/articles/{article.id}", status_code=status.HTTP_302_FOUND)


@app.get("/articles", response_class=HTMLResponse)
async def articles_list(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    articles = db.query(Article).filter(Article.user_id == user.id).order_by(Article.created_at.desc()).all()
    return render_template(request, "articles.html", user=user, articles=articles)


@app.get("/articles/{article_id}", response_class=HTMLResponse)
async def article_detail(request: Request, article_id: int, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    article = db.query(Article).filter(Article.id == article_id, Article.user_id == user.id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    return render_template(request, "article_detail.html", user=user, article=article)


# ---------------- Lemon Squeezy Payments ----------------

@app.post("/create-checkout-session")
async def create_checkout_session(
    request: Request,
    plan: str = Form(...),
    db: Session = Depends(get_db)
):
    """
    Create a Lemon Squeezy Checkout session for the selected plan.
    Maps plan name to the corresponding Lemon Squeezy variant ID.
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    # Map plan to Lemon Squeezy variant ID
    if plan == "creator":
        variant_id = LEMONSQUEEZY_VARIANT_ID_CREATOR
    elif plan == "pro":
        variant_id = LEMONSQUEEZY_VARIANT_ID_PRO
    else:
        return JSONResponse({"error": "Invalid plan selected"}, status_code=400)

    if not variant_id:
        return JSONResponse({"error": "Plan variant not configured. Please set LEMONSQUEEZY_VARIANT_ID_CREATOR or LEMONSQUEEZY_VARIANT_ID_PRO."}, status_code=400)

    if not LEMONSQUEEZY_STORE_ID:
        return JSONResponse({"error": "Store not configured. Please set LEMONSQUEEZY_STORE_ID."}, status_code=400)

    try:
        # Build the checkout data according to Lemon Squeezy API spec
        checkout_data = {
            "data": {
                "type": "checkouts",
                "attributes": {
                    "checkout_options": {
                        "embed": False,
                        "media": False,
                        "logo": None,
                        "desc": None,
                        "cancel_url": f"{APP_URL}/pricing",
                        "success_url": f"{APP_URL}/success?order_id={{order_id}}",
                        "checkout_data": {
                            "user_id": str(user.id),
                            "plan": plan,
                            "email": user.email,
                        },
                    },
                    "checkout_custom_value": {
                        "user_id": str(user.id),
                        "plan": plan,
                    },
                    "product_options": {
                        "name": None,
                        "description": None,
                        "receipt_button_text": None,
                        "receipt_thank_you_note": None,
                    },
                },
                "relationships": {
                    "store": {
                        "data": {
                            "type": "stores",
                            "id": LEMONSQUEEZY_STORE_ID,
                        }
                    },
                    "variant": {
                        "data": {
                            "type": "variants",
                            "id": variant_id,
                        }
                    }
                }
            }
        }

        result = await lemonsqueezy_post("/checkouts", checkout_data)

        # Extract the checkout URL from the response
        checkout_url = result.get("data", {}).get("attributes", {}).get("url")

        if not checkout_url:
            return JSONResponse({"error": "Failed to create checkout session"}, status_code=400)

        return RedirectResponse(url=checkout_url, status_code=303)

    except httpx.HTTPStatusError as e:
        return JSONResponse({"error": f"Lemon Squeezy API error: {e.response.text}"}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.get("/success")
async def payment_success(request: Request, order_id: str = None, db: Session = Depends(get_db)):
    """
    Handle successful payment redirect from Lemon Squeezy.
    The actual subscription activation is handled by the webhook,
    but this page confirms the purchase to the user.
    """
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    # Optionally fetch order details from Lemon Squeezy API
    # The webhook will handle the actual subscription update
    if order_id:
        try:
            order_data = await lemonsqueezy_get(f"/orders/{order_id}")
            order_attrs = order_data.get("data", {}).get("attributes", {})
            subscription_id = None

            # Check if there's a subscription in the order
            relationships = order_data.get("data", {}).get("relationships", {})
            if "subscription" in relationships:
                sub_data = relationships["subscription"].get("data", {})
                subscription_id = sub_data.get("id")

            if subscription_id:
                user.lemonsqueezy_subscription_id = str(subscription_id)

            # Try to get the customer email from the order
            customer_email = order_attrs.get("user_email") or order_attrs.get("customer_email")
            if customer_email:
                user.email = customer_email

            user.subscription_status = "active"
            db.commit()
        except Exception:
            pass  # Webhook will handle the update

    return render_template(request, "success.html", user=user)


def verify_lemonsqueezy_webhook(payload: bytes, x_signature: str) -> bool:
    """
    Verify the Lemon Squeezy webhook signature.
    Lemon Squeezy uses HMAC-SHA256 to sign webhook payloads.
    The signature is passed in the X-Signature header.
    """
    if not LEMONSQUEEZY_WEBHOOK_SECRET:
        # In development, you may want to skip verification
        if DEBUG:
            return True
        return False

    computed_signature = hmac.new(
        LEMONSQUEEZY_WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(computed_signature, x_signature)


@app.post("/webhook")
async def lemonsqueezy_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Handle Lemon Squeezy webhook events.

    Supported events:
    - order_created: New order/placement
    - subscription_created: New subscription activated
    - subscription_updated: Subscription status change (e.g., renewal)
    - subscription_cancelled: Subscription canceled
    - subscription_expired: Subscription expired
    """
    payload = await request.body()
    x_signature = request.headers.get("X-Signature", "")

    # Verify webhook signature
    if not verify_lemonsqueezy_webhook(payload, x_signature):
        return JSONResponse({"error": "Invalid signature"}, status_code=400)

    try:
        event = json.loads(payload)
    except json.JSONDecodeError:
        return JSONResponse({"error": "Invalid JSON payload"}, status_code=400)

    event_name = event.get("meta", {}).get("event_name", "")
    event_data = event.get("data", {})
    attrs = event_data.get("attributes", {})

    if event_name == "subscription_created":
        # New subscription activated
        subscription_id = str(event_data.get("id"))
        customer_id = str(attrs.get("customer_id", ""))
        status = attrs.get("status", "")
        plan_name = attrs.get("variant_name", "")
        user_email = attrs.get("user_email", "")
        ends_at = attrs.get("ends_at")  # ISO 8601 string or None for recurring
        renews_at = attrs.get("renews_at")  # ISO 8601 string

        # Map variant name to plan
        plan = _map_variant_to_plan(plan_name)

        # Find user by email or by customer_id stored in checkout_data
        user = _find_user_by_email_or_customer(db, user_email, customer_id)

        if user:
            user.lemonsqueezy_subscription_id = subscription_id
            user.lemonsqueezy_customer_id = customer_id
            user.plan = plan
            user.subscription_status = status
            if renews_at:
                try:
                    user.subscription_end_date = datetime.fromisoformat(renews_at.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    pass
            db.commit()

    elif event_name == "subscription_updated":
        # Subscription updated (e.g., plan change, renewal)
        subscription_id = str(event_data.get("id"))
        customer_id = str(attrs.get("customer_id", ""))
        status = attrs.get("status", "")
        plan_name = attrs.get("variant_name", "")
        renews_at = attrs.get("renews_at")

        plan = _map_variant_to_plan(plan_name)
        user = db.query(User).filter(User.lemonsqueezy_subscription_id == subscription_id).first()

        if not user:
            user = db.query(User).filter(User.lemonsqueezy_customer_id == customer_id).first()

        if user:
            user.plan = plan
            user.subscription_status = status
            if renews_at:
                try:
                    user.subscription_end_date = datetime.fromisoformat(renews_at.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    pass
            db.commit()

    elif event_name == "subscription_cancelled":
        # Subscription canceled
        subscription_id = str(event_data.get("id"))
        customer_id = str(attrs.get("customer_id", ""))
        status = attrs.get("status", "cancelled")
        ends_at = attrs.get("ends_at")  # When access ends

        user = db.query(User).filter(User.lemonsqueezy_subscription_id == subscription_id).first()

        if not user:
            user = db.query(User).filter(User.lemonsqueezy_customer_id == customer_id).first()

        if user:
            user.subscription_status = "canceled"
            if ends_at:
                try:
                    user.subscription_end_date = datetime.fromisoformat(ends_at.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    pass
            else:
                user.plan = "free"
                user.lemonsqueezy_subscription_id = None
            db.commit()

    elif event_name == "subscription_expired":
        # Subscription expired
        subscription_id = str(event_data.get("id"))
        customer_id = str(attrs.get("customer_id", ""))

        user = db.query(User).filter(User.lemonsqueezy_subscription_id == subscription_id).first()

        if not user:
            user = db.query(User).filter(User.lemonsqueezy_customer_id == customer_id).first()

        if user:
            user.plan = "free"
            user.subscription_status = "expired"
            user.lemonsqueezy_subscription_id = None
            user.subscription_end_date = None
            db.commit()

    elif event_name == "order_created":
        # Order created (can be used for one-time or initial subscription)
        order_id = str(event_data.get("id"))
        order_status = attrs.get("status", "")
        user_email = attrs.get("user_email", "")
        customer_id = str(attrs.get("customer_id", ""))

        # Store order ID if we can find the user
        user = _find_user_by_email_or_customer(db, user_email, customer_id)

        if user:
            user.lemonsqueezy_order_id = order_id
            db.commit()

    return JSONResponse({"status": "success"})


def _map_variant_to_plan(variant_name: str) -> str:
    """
    Map Lemon Squeezy variant name to internal plan name.
    Adjust these mappings to match your Lemon Squeezy product variant names.
    """
    if not variant_name:
        return "free"

    variant_lower = variant_name.lower()
    if "creator" in variant_lower:
        return "creator"
    elif "pro" in variant_lower:
        return "pro"
    else:
        return "free"


def _find_user_by_email_or_customer(db: Session, email: str, customer_id: str) -> Optional[User]:
    """
    Find a user by email or Lemon Squeezy customer ID.
    """
    user = None
    if email:
        user = db.query(User).filter(User.email == email).first()
    if not user and customer_id:
        user = db.query(User).filter(User.lemonsqueezy_customer_id == customer_id).first()
    return user


@app.post("/cancel-subscription")
async def cancel_subscription(request: Request, db: Session = Depends(get_db)):
    """
    Cancel the user's Lemon Squeezy subscription via API.
    """
    user = get_current_user(request, db)
    if not user or not user.lemonsqueezy_subscription_id:
        return RedirectResponse(url="/dashboard", status_code=302)

    try:
        await lemonsqueezy_delete(f"/subscriptions/{user.lemonsqueezy_subscription_id}")
        user.plan = "free"
        user.subscription_status = "canceled"
        user.lemonsqueezy_subscription_id = None
        user.subscription_end_date = None
        db.commit()
    except httpx.HTTPStatusError as e:
        # Log the error but still update locally
        print(f"Lemon Squeezy cancel error: {e.response.text}")
    except Exception as e:
        print(f"Lemon Squeezy cancel error: {e}")

    return RedirectResponse(url="/dashboard?canceled=true", status_code=302)


# ---------------- Admin Panel ----------------

@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request, db: Session = Depends(get_db)):
    user = require_admin(request, db)

    total_users = db.query(User).count()
    total_articles = db.query(Article).count()
    active_subscriptions = db.query(User).filter(User.subscription_status == "active").count()

    recent_users = db.query(User).order_by(User.created_at.desc()).limit(10).all()
    recent_articles = db.query(Article).order_by(Article.created_at.desc()).limit(10).all()

    # Plan distribution
    plan_counts = {}
    for p in ["free", "creator", "pro"]:
        plan_counts[p] = db.query(User).filter(User.plan == p).count()

    return render_template(request, "admin.html", user=user, total_users=total_users, total_articles=total_articles, active_subscriptions=active_subscriptions, recent_users=recent_users, recent_articles=recent_articles, plan_counts=plan_counts)


# ---------------- API Routes (Pro Plan) ----------------

@app.get("/api/articles")
async def api_articles(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    if user.plan != "pro":
        raise HTTPException(status_code=403, detail="API access requires Pro plan")

    articles = db.query(Article).filter(Article.user_id == user.id).all()
    return [
        {
            "id": a.id,
            "title": a.title,
            "keyword": a.keyword,
            "word_count": a.word_count,
            "created_at": a.created_at.isoformat()
        }
        for a in articles
    ]


@app.get("/api/articles/{article_id}")
async def api_article_detail(article_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    if user.plan != "pro":
        raise HTTPException(status_code=403, detail="API access requires Pro plan")

    article = db.query(Article).filter(Article.id == article_id, Article.user_id == user.id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    return {
        "id": article.id,
        "title": article.title,
        "keyword": article.keyword,
        "content": article.content,
        "meta_description": article.meta_description,
        "tags": article.tags,
        "word_count": article.word_count,
        "created_at": article.created_at.isoformat()
    }


# ---------------- Health Check ----------------

@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.1.0", "payment_provider": "lemonsqueezy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=DEBUG)
