import streamlit as st
from scraper_engine import scrape_site, SAFE_DEFAULTS, ALLOWED_DEMO_DOMAINS, validate_target_url

st.set_page_config(page_title="Web Scraping Lab", page_icon="🧾", layout="wide")
st.title("Web Scraping Lab")
st.caption("Student-safe public web scraping demo. Use only public pages you are permitted to access.")

with st.expander("What this app does"):
    st.markdown("""
- Paste a public webpage URL
- Choose a small page limit and crawl depth
- Extract page titles, links and public document links
- Download supported public documents
- Export an Excel report and ZIP package
- Block local/private/internal network targets
- Respect robots.txt
- No login/CAPTCHA/OTP/paywall bypass
""")

st.sidebar.header("Classroom Safety Limits")
st.sidebar.info(
    f"Max pages: {SAFE_DEFAULTS['MAX_PAGES_CAP']}\n\n"
    f"Max depth: {SAFE_DEFAULTS['MAX_DEPTH_CAP']}\n\n"
    f"Max documents: {SAFE_DEFAULTS['MAX_DOCUMENTS_CAP']}\n\n"
    f"Max file size: {SAFE_DEFAULTS['MAX_FILE_MB']} MB\n\n"
    "External domains: OFF\n\nrobots.txt: ON"
)

mode = st.radio(
    "Website access mode",
    ["Any public website", "Recommended classroom websites only"],
    horizontal=True,
)

if mode == "Recommended classroom websites only":
    st.code("\n".join(ALLOWED_DEMO_DOMAINS))

url = st.text_input("Website URL", placeholder="https://example.gov.in/page")

c1, c2, c3 = st.columns(3)
with c1:
    max_pages = st.number_input("Max pages", 1, SAFE_DEFAULTS["MAX_PAGES_CAP"], 5)
with c2:
    max_depth = st.number_input("Crawl depth", 0, SAFE_DEFAULTS["MAX_DEPTH_CAP"], 1)
with c3:
    max_documents = st.number_input("Max documents", 1, SAFE_DEFAULTS["MAX_DOCUMENTS_CAP"], 50)

delay = st.slider("Delay between requests (seconds)", 1.0, 3.0, 1.0, 0.5)
save_html = st.checkbox("Save webpage HTML", value=False)
save_text = st.checkbox("Save webpage text", value=True)

st.warning(
    "This hosted classroom version intentionally excludes login, OTP, CAPTCHA, "
    "authenticated sessions, Playwright browser automation and external-domain crawling."
)

if st.button("START SCRAPING", type="primary", use_container_width=True):
    ok, message = validate_target_url(
        url,
        restrict_to_demo_domains=(mode == "Recommended classroom websites only")
    )
    if not ok:
        st.error(message)
        st.stop()

    progress = st.progress(0)
    status = st.empty()

    def progress_cb(done, total, message):
        progress.progress(min(done / max(total, 1), 1.0))
        status.write(message)

    try:
        result = scrape_site(
            start_url=url,
            max_pages=int(max_pages),
            max_depth=int(max_depth),
            max_documents=int(max_documents),
            delay_seconds=float(delay),
            save_html=save_html,
            save_text=save_text,
            progress_callback=progress_cb,
        )
    except Exception as exc:
        st.error(f"Scraping failed: {exc}")
        st.stop()

    progress.progress(1.0)
    status.success("Scraping completed.")

    a, b, c, d = st.columns(4)
    a.metric("Pages processed", result["summary"]["pages_processed"])
    b.metric("Documents found", result["summary"]["documents_found"])
    c.metric("Downloaded", result["summary"]["downloaded"])
    d.metric("Failed / skipped", result["summary"]["failed_or_skipped"])

    st.subheader("Pages")
    st.dataframe(result["pages_df"], use_container_width=True, hide_index=True)

    st.subheader("Documents")
    st.dataframe(result["documents_df"], use_container_width=True, hide_index=True)

    st.download_button(
        "Download Excel Report",
        data=result["excel_bytes"],
        file_name="Web_Scraping_Report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

    st.download_button(
        "Download Complete ZIP",
        data=result["zip_bytes"],
        file_name="Web_Scraping_Output.zip",
        mime="application/zip",
        use_container_width=True,
    )

st.divider()
st.caption(
    "A page being visible in a browser does not guarantee automated scraping is permitted "
    "or technically available. Respect site terms, robots.txt and rate limits."
)
