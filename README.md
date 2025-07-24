# Schema Generator LLM

This project provides a Streamlit application that generates production ready [Schema.org](https://schema.org) JSON-LD markup. The app analyzes a web page, detects the page type, and uses Google Gemini to create or improve schema markup. It includes templates for common schemas, quality scoring, and entity intelligence via Wikipedia.

## Setup

1. Clone the repository
2. (Optional) Create a virtual environment and activate it
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Provide a Google Gemini API key via the `GEMINI_API_KEY` environment variable or by adding it to `~/.streamlit/secrets.toml`:
   ```toml
   GEMINI_API_KEY = "your-secret-key"
   ```

## Running the App

Start the Streamlit server from the repository root:

```bash
streamlit run app.py
```

The interface lets you enter a URL, pick the page type and schema template, and generates JSON-LD that you can copy into your site.

## Example Use

```bash
$ streamlit run app.py
```
Navigate to the local URL provided by Streamlit in your browser, supply a web page URL, then click **"Generate Comprehensive Schema"**. The generated markup appears in the interface along with quality metrics.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
