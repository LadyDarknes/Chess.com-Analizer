import os
import time
import random
import logging
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

import config
from engine import Stockfish, Maia
from board import get_stable_board_fen, is_game_over, is_player_turn, detect_player_color, get_opponent_elo, wait_for_board_ready
from overlay import setup_f4_listener, clear_overlay, draw_moves

# ANSI Escape Codes for console coloring
CLR_RESET = "\033[0m"
CLR_CYAN = "\033[96m"
CLR_PINK = "\033[95m"
CLR_YELLOW = "\033[93m"
CLR_GREEN = "\033[92m"
CLR_RED = "\033[91m"
CLR_BOLD = "\033[1m"

# Enable VT100/ANSI support in Windows Console
if os.name == 'nt':
    os.system('')

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("analyzer")

def inject_driver():
    options = Options()
    options.add_experimental_option("debuggerAddress", config.DEBUGGER_ADDRESS)
    return webdriver.Chrome(options=options)

def main():
    driver = inject_driver()
    logger.info("Connected to browser session.")
    
    setup_f4_listener(driver)
    stockfish = Stockfish()
    maia = None
    
    player_color = 'w'
    opponent_elo = 1900
    last_fen = "start"
    game_is_active = True
    move_count = 1
    
    logger.info("Starting analyzer loop...")
    wait_for_board_ready(driver)
    time.sleep(1)
    
    player_color = detect_player_color(driver)
    opponent_elo = get_opponent_elo(driver)
    
    model_elo = min(config.AVAILABLE_MAIA_MODELS, key=lambda x: abs(x - opponent_elo))
    maia = Maia(f"{config.MAIA_DIR}/maia-{model_elo}.pb.gz")
    
    # Initial console clear and setup print
    os.system('cls' if os.name == 'nt' else 'clear')
    color_text = "Beyaz" if player_color == 'w' else "Siyah"
    print(f"{CLR_CYAN}{CLR_BOLD}========================================{CLR_RESET}")
    print(f"   {CLR_GREEN}{CLR_BOLD}CHESS.COM ANALYZER - OYUN BAŞLADI{CLR_RESET}")
    print(f"   Renk: {CLR_BOLD}{color_text}{CLR_RESET} | ELO: {CLR_BOLD}{opponent_elo}{CLR_RESET} | Model: {CLR_BOLD}Maia-{model_elo}{CLR_RESET}")
    print(f"{CLR_CYAN}{CLR_BOLD}========================================{CLR_RESET}\n")

    while True:
        try:
            game_over = is_game_over(driver)
            
            if game_over:
                if game_is_active:
                    print(f"\n{CLR_RED}{CLR_BOLD}[SİSTEM] Oyun bitti. Yeni oyun bekleniyor...{CLR_RESET}")
                    clear_overlay(driver)
                    game_is_active = False
                time.sleep(2)
                continue
            
            if not game_is_active:
                logger.info("New game detected. Waiting for board to load...")
                wait_for_board_ready(driver)
                time.sleep(1)
                
                player_color = detect_player_color(driver)
                opponent_elo = get_opponent_elo(driver)
                model_elo = min(config.AVAILABLE_MAIA_MODELS, key=lambda x: abs(x - opponent_elo))
                
                if maia:
                    maia.stop()
                maia = Maia(f"{config.MAIA_DIR}/maia-{model_elo}.pb.gz")
                
                # Reset move count and clear console for the new game
                move_count = 1
                os.system('cls' if os.name == 'nt' else 'clear')
                color_text = "Beyaz" if player_color == 'w' else "Siyah"
                print(f"{CLR_CYAN}{CLR_BOLD}========================================{CLR_RESET}")
                print(f"   {CLR_GREEN}{CLR_BOLD}CHESS.COM ANALYZER - YENİ OYUN BAŞLADI{CLR_RESET}")
                print(f"   Renk: {CLR_BOLD}{color_text}{CLR_RESET} | ELO: {CLR_BOLD}{opponent_elo}{CLR_RESET} | Model: {CLR_BOLD}Maia-{model_elo}{CLR_RESET}")
                print(f"{CLR_CYAN}{CLR_BOLD}========================================{CLR_RESET}\n")
                
                game_is_active = True
                last_fen = "reset"
            
            # Dynamically verify and update player color if it changes
            detected_color = detect_player_color(driver)
            if detected_color != 'unk' and detected_color != player_color:
                logger.info(f"Player color corrected: {player_color} -> {detected_color}")
                player_color = detected_color
                os.system('cls' if os.name == 'nt' else 'clear')
                color_text = "Beyaz" if player_color == 'w' else "Siyah"
                print(f"{CLR_CYAN}{CLR_BOLD}========================================{CLR_RESET}")
                print(f"   {CLR_GREEN}{CLR_BOLD}CHESS.COM ANALYZER - OYUN BAŞLADI{CLR_RESET}")
                print(f"   Renk: {CLR_BOLD}{color_text}{CLR_RESET} | ELO: {CLR_BOLD}{opponent_elo}{CLR_RESET} | Model: {CLR_BOLD}Maia-{model_elo}{CLR_RESET}")
                print(f"{CLR_CYAN}{CLR_BOLD}========================================{CLR_RESET}\n")
                last_fen = "reset"

            if is_player_turn(driver, player_color):
                time.sleep(0.2)
                current_fen = get_stable_board_fen(driver)
                
                if current_fen and current_fen != last_fen:
                    maia_moves = maia.get_top_moves(current_fen, player_color)
                    best_move = stockfish.get_best_move(current_fen, player_color)
                    
                    if len(maia_moves) > 1 and random.random() < 0.15:
                        maia_moves.pop(0)

                    # Print a beautiful card for the move
                    print(f"{CLR_CYAN}────────────────────────────────────────{CLR_RESET}")
                    print(f"{CLR_YELLOW}{CLR_BOLD}[Hamle {move_count}]{CLR_RESET} Hamle Sırası Sizde!")
                    print(f"  {CLR_GREEN}★ Önerilen (Stockfish):{CLR_RESET} {CLR_BOLD}{best_move}{CLR_RESET}")
                    print(f"  {CLR_PINK}👤 İnsansı Öneriler (Maia):{CLR_RESET}")
                    for idx, m in enumerate(maia_moves, 1):
                        print(f"     {idx}. {m}")
                    print(f"{CLR_CYAN}────────────────────────────────────────{CLR_RESET}\n")
                    
                    draw_moves(driver, maia_moves, best_move, player_color == 'b')
                    last_fen = current_fen
                    move_count += 1
                elif current_fen is None:
                    time.sleep(0.5)
            else:
                clear_overlay(driver)
                time.sleep(0.5)
                
            time.sleep(0.1)

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"{CLR_RED}[HATA] Beklenmeyen hata oluştu: {e}{CLR_RESET}")
            time.sleep(1)

    if maia:
        maia.stop()
    stockfish.stop()

if __name__ == "__main__":
    main()