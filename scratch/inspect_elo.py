from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

def main():
    options = Options()
    options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
    driver = webdriver.Chrome(options=options)
    
    print("Page Title:", driver.title)
    
    # Let's search for player components in the DOM
    selectors = [
        ".player-component",
        "[class*='player-component']",
        ".player-info",
        "[class*='player-info']",
        ".player-tagline",
        "[class*='player']"
    ]
    
    for sel in selectors[:5]:
        elements = driver.find_elements(By.CSS_SELECTOR, sel)
        print(f"\nSelector '{sel}' found {len(elements)} elements:")
        for idx, el in enumerate(elements):
            text = el.text.strip().replace('\n', ' | ')
            print(f"  El {idx}: tag={el.tag_name}, class='{el.get_attribute('class')}', text='{text}'")
            
    # Specifically inspect what top panel is
    print("\nEvaluating top panel innerText directly:")
    top_panel_text = driver.execute_script("""
        const el = document.querySelector('.player-component.top');
        return el ? { html: el.outerHTML, text: el.innerText } : null;
    """)
    print("Top Panel:", top_panel_text)

if __name__ == "__main__":
    main()
