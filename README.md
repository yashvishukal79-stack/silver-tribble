# Web Scraping Lab - Student Safe Streamlit Edition

This free classroom app lets students paste a public webpage URL, choose a small page limit and crawl depth, extract public document links, download supported files, and export Excel/ZIP results.

## Safety limits
- Maximum 20 pages
- Maximum crawl depth 2
- Maximum 100 documents
- Maximum 25 MB per file
- Minimum 1 second delay
- Same registered domain only
- Private/local/internal IP addresses blocked
- robots.txt respected
- No login, OTP, CAPTCHA, paywall or anti-bot bypass

## Free deployment
1. Create a free GitHub account.
2. Create a public repository named `web-scraping-lab`.
3. Upload `app.py`, `scraper_engine.py`, `requirements.txt`, `README.md` and `.streamlit/config.toml`.
4. Open `https://share.streamlit.io`.
5. Sign in with GitHub.
6. Create app.
7. Repository: `yourusername/web-scraping-lab`
8. Branch: `main`
9. Entrypoint: `app.py`
10. Deploy and share the generated `streamlit.app` URL.

Recommended demo domains:
- cbic-gst.gov.in
- taxinformation.cbic.gov.in
- sebi.gov.in
- cercind.gov.in
- dea.gov.in
- financialservices.gov.in
