#!/bin/bash
# ARIA Real Estate Agent — Setup Script

set -e
echo "Setting up ARIA Real Estate Agent..."

# Create virtual environment
cd "$(dirname "$0")"
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Copy env file if not exists
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env file — open it and add your API keys!"
fi

# Create data directories
mkdir -p data/documents data/templates

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Edit .env and add your API keys:"
echo "     - ANTHROPIC_API_KEY (required for AI features)"
echo "     - TAVILY_API_KEY (required for live market research)"
echo "     - SENDGRID_API_KEY (optional, for email)"
echo ""
echo "  2. Start the app:"
echo "     source venv/bin/activate"
echo "     cd backend && uvicorn main:app --reload --port 8000"
echo ""
echo "  3. Open in browser: http://localhost:8000"
echo "     API docs: http://localhost:8000/docs"
