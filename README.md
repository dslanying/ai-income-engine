# SEOWriter - AI SEO Content Generator

A production-ready micro-SaaS application that generates SEO-optimized blog articles using AI. Built with Python FastAPI, SQLite, and Tailwind CSS.

## Features

- **AI Content Generation**: Enter any keyword and get a complete, structured SEO article
- **User Authentication**: Session-based auth with registration and login
- **Subscription Plans**: Free (3 articles/month), Pro ($9/month unlimited), Business ($29/month with API)
- **Stripe Payments**: Integrated checkout and subscription management
- **Admin Panel**: View user stats, recent activity, and revenue metrics
- **Article Management**: View history, copy content, download as Markdown
- **API Access**: REST API for Business plan users

## Tech Stack

- **Backend**: Python 3.9+, FastAPI, SQLAlchemy
- **Frontend**: HTML + Tailwind CSS (CDN)
- **Database**: SQLite (production-ready, can swap to PostgreSQL)
- **Payments**: Stripe Checkout + Webhooks
- **Deployment**: Uvicorn/Gunicorn

## Quick Start

### 1. Clone and Install

```bash
cd microsaas
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```env
SECRET_KEY=your-super-secret-key-here
DEBUG=false

# Stripe (Get from https://dashboard.stripe.com/test/apikeys)
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...

# Create products in Stripe Dashboard, then add price IDs
STRIPE_PRICE_ID_PRO=price_...
STRIPE_PRICE_ID_BUSINESS=price_...

# Admin email for accessing /admin
ADMIN_EMAIL=your-email@example.com
```

### 3. Run Development Server

```bash
python main.py
```

Or with uvicorn directly:

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Visit http://localhost:8000

## Production Deployment

### Using Gunicorn + Uvicorn Workers

```bash
pip install gunicorn

gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### Using Systemd (Linux)

Create `/etc/systemd/system/seowriter.service`:

```ini
[Unit]
Description=SEOWriter App
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/seowriter
Environment="PATH=/opt/seowriter/venv/bin"
EnvironmentFile=/opt/seowriter/.env
ExecStart=/opt/seowriter/venv/bin/gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable seowriter
sudo systemctl start seowriter
```

### Using Docker

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
EXPOSE 8000

CMD ["gunicorn", "main:app", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000"]
```

### Using Docker Compose

```yaml
version: '3.8'
services:
  app:
    build: .
    ports:
      - "8000:8000"
    env_file:
      - .env
    volumes:
      - ./data:/app
```

## Stripe Setup Guide

1. Create a Stripe account at https://stripe.com
2. Switch to Test Mode
3. Go to Products > Add Product
   - Create "Pro Plan" ($9/month)
   - Create "Business Plan" ($29/month)
4. Copy the Price IDs to your `.env` file
5. Get your API keys from Developers > API Keys
6. For webhooks (optional but recommended):
   - Go to Developers > Webhooks
   - Add endpoint: `https://yourdomain.com/webhook`
   - Select events: `invoice.payment_succeeded`, `customer.subscription.deleted`, `invoice.payment_failed`
   - Copy the webhook signing secret to `.env`

## API Documentation

Business plan users get API access:

### Authentication
API uses the same session cookie as the web app.

### Endpoints

**List Articles**
```
GET /api/articles
```

**Get Article Detail**
```
GET /api/articles/{article_id}
```

## Customization

### Adding Real AI Integration

The app currently uses a high-quality template system. To integrate a real AI API (OpenAI, Claude, etc.):

1. Add your AI provider to `requirements.txt`
2. Modify the `SEOContentGenerator.generate()` method in `main.py`:

```python
import openai

@classmethod
def generate(cls, keyword: str) -> dict:
    prompt = f"Write a comprehensive SEO-optimized blog article about: {keyword}"
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}]
    )
    content = response.choices[0].message.content
    # ... parse and return structured data
```

### Changing Plans/Pricing

Edit the `PLANS` dictionary in `main.py`:

```python
PLANS = {
    "free": {...},
    "pro": {...},
    "business": {...}
}
```

### Database Migration

To use PostgreSQL instead of SQLite:

1. Update `.env`:
   ```
   DATABASE_URL=postgresql://user:password@localhost/seowriter
   ```
2. Install psycopg2: `pip install psycopg2-binary`
3. Run the app - tables are auto-created

## File Structure

```
microsaas/
├── main.py                 # FastAPI application
├── models.py               # SQLAlchemy database models
├── requirements.txt        # Python dependencies
├── .env.example            # Environment variables template
├── README.md               # This file
├── templates/              # Jinja2 HTML templates
│   ├── base.html
│   ├── index.html
│   ├── pricing.html
│   ├── login.html
│   ├── register.html
│   ├── dashboard.html
│   ├── generate.html
│   ├── articles.html
│   ├── article_detail.html
│   ├── success.html
│   └── admin.html
└── static/                 # Static assets (if needed)
```

## Security Considerations

- Change `SECRET_KEY` in production
- Use HTTPS in production (Stripe requires this)
- Set `DEBUG=false` in production
- Regularly update dependencies
- Consider adding rate limiting for article generation
- The admin panel is protected by email check - consider a more robust RBAC system for larger deployments

## License

MIT License - Feel free to use this as a starting point for your own SaaS.

## Support

For issues or questions, open a GitHub issue or contact support.
