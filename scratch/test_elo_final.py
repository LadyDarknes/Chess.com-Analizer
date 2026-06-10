from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import sys
sys.path.append(".")
from board import get_opponent_elo

def main():
    options = Options()
    options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
    driver = webdriver.Chrome(options=options)
    
    print("Parsed Opponent ELO:", get_opponent_elo(driver))

if __name__ == "__main__":
    main()
