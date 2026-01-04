from langchain_core.messages import AIMessage
import json
import re
import requests
import warnings
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from concurrent.futures import ThreadPoolExecutor

# Suppress only the single warning from urllib3 needed.
warnings.simplefilter('ignore', InsecureRequestWarning)

def verify_url(url):
    try:
        # Use requests library instead of curl for better portability across OS
        # mimicking the headers we found effective
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.google.com/',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'cross-site',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0'
        }

        # Use GET with stream=True to check headers/status without downloading full body
        # verify=False is equivalent to curl -k (insecure)
        response = requests.get(url, headers=headers, timeout=15, stream=True, verify=False)
        
        status_code = response.status_code

        # Treat 403 as potentially accessible but blocked by WAF
        if 200 <= status_code < 400:
            return url, "VALID"
        elif status_code == 404:
            return url, "NOT FOUND (404)"
        elif status_code == 403:
             return url, "VALID (Protected/403)" 
        else:
            return url, f"ACCESSIBLE (Status: {status_code})"

    except Exception as e:
        # Fallback error handling
        return url, f"ERROR (Could not access: {str(e)})"

def get_unique_urls(text):
    if not text:
        return []
    # Simple regex to find URLs
    urls = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', text)
    # Remove duplicates and clean trailing punctuation
    clean_urls = []
    for url in urls:
        # Strip common trailing punctuation that might be captured
        url = url.rstrip(').,;]')
        clean_urls.append(url)
    
    return list(set(clean_urls))

def check_urls_and_get_data(text, source_label):
    unique_urls = get_unique_urls(text)
    
    if not unique_urls:
        return []
        
    results = []
    # Limit max workers to avoid being flagged as DoS
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(verify_url, url) for url in unique_urls]
        for future in futures:
            url, status = future.result()
            results.append({
                "url": url,
                "status": status,
                "source": source_label
            })
    return results

def create_fact_checker(llm):
    def fact_checker_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        current_response = investment_debate_state.get("current_response", "")
        
        # Reports to verify against
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        
        # If there's no response to check, pass
        if not current_response:
            return {}
            
        # Verify URLs - collect structured data
        verified_data = []
        
        # 1. Check URLs in News Report
        news_verified = check_urls_and_get_data(news_report, "News Analyst")
        verified_data.extend(news_verified)
        
        # 2. Check URLs in Current Response (Debate)
        response_verified = check_urls_and_get_data(current_response, "Debate Speaker")
        verified_data.extend(response_verified)
        
        # Deduplicate by URL (keep first occurrence or merge sources)
        unique_verified_map = {}
        for item in verified_data:
            if item["url"] not in unique_verified_map:
                unique_verified_map[item["url"]] = item
            else:
                # If already exists, append source if different
                if item["source"] not in unique_verified_map[item["url"]]["source"]:
                    unique_verified_map[item["url"]]["source"] += f", {item['source']}"
        
        final_verified_list = list(unique_verified_map.values())

        # Generate text report for LLM prompt
        url_check_report = ""
        if final_verified_list:
            url_check_report = "\n[URL Verification Report]\n"
            for item in final_verified_list:
                url_check_report += f"- {item['url']}: {item['status']} (Source: {item['source']})\n"
            
            print(f"DEBUG: URL Verification completed.\n{url_check_report}")

        prompt = f"""You are a strict Fact Checker for a financial analysis team.
Your job is to verify the claims made in the following statement against the provided source reports AND verify the validity of the sources.

Statement to Verify:
"{current_response}"

Source Reports:
1. Market Research: {market_research_report}
2. Sentiment Report: {sentiment_report}
3. News Report: {news_report}
4. Fundamentals Report: {fundamentals_report}

URL Verification Status (Physical Check of Links):
{url_check_report}

Instructions:
1. Extract every factual claim (numbers, dates, specific news events) from the statement.
2. Check if each claim exists in the Source Reports.
3. **CRITICAL**: Check the "URL Verification Status" section. If the statement relies on a news article whose URL is marked as "NOT FOUND", "ERROR", or "INVALID", you MUST flag this as a potential invalid source or deleted article.
4. If a claim is NOT found or contradicts the reports, flag it as a HALLUCINATION.
5. If the statement is mostly opinion/analysis, it is acceptable.
6. **ALWAYS** list the Verified Sources (URLs) at the end of your response, even if verified.

Output Format:
If all facts are supported and sources are valid:
"VERIFIED: The statement is consistent with the provided data and sources appear valid.

[Verified Sources]
- [URL1] (Status: VALID)
...
"

If errors are found:
"CORRECTION NEEDED:
- Claim: [Claim] -> Error: [Not found / Contradiction / Source URL Invalid or Deleted]
...

[Verified Sources]
- [URL1] (Status: ...)
...
"

Be extremely strict about numbers. If revenue is 10B in reports but statement says 12B, flag it.
Be strict about source validity. If a key argument is based on a broken link, flag it.
"""
        
        response = llm.invoke(prompt)
        check_result = response.content
        
        # Log the fact check result
        print(f"\n\n[Fact Checker]:\n{check_result}\n")
        
        # Prepare state update
        new_state = investment_debate_state.copy()
        
        # Merge existing verified urls with new ones
        existing_verified = new_state.get("verified_urls", [])
        # We want to accumulate unique URLs seen so far
        existing_url_map = {item['url']: item for item in existing_verified}
        for item in final_verified_list:
             existing_url_map[item['url']] = item
        new_state["verified_urls"] = list(existing_url_map.values())
        
        if "CORRECTION NEEDED" in check_result:
            updated_response = f"{current_response}\n\n[SYSTEM NOTE: Fact Check Warning]\n{check_result}"
            new_state["current_response"] = updated_response
            new_state["history"] += f"\n\n[Fact Check Warning]: {check_result}"
            return {"investment_debate_state": new_state}
            
        elif "VERIFIED" in check_result and url_check_report:
            new_state["history"] += f"\n\n[Fact Checker]: {check_result}"
            return {"investment_debate_state": new_state}
        
        # Even if no text update, we return state to save verified_urls
        return {"investment_debate_state": new_state}

    return fact_checker_node
