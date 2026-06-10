import re
import time
from selenium.webdriver.common.by import By

def wait_for_board_ready(driver, timeout=10):
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            pieces = driver.find_elements(By.CSS_SELECTOR, "div.piece")
            if len(pieces) >= 16:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False

def get_board_fen(driver):
    try:
        pieces = driver.find_elements(By.CSS_SELECTOR, "div.piece")
        board = [[None] * 8 for _ in range(8)]
        
        for piece in pieces:
            piece_class = piece.get_attribute("class")
            square_match = re.search(r'square-(\d)(\d)', piece_class)
            if not square_match:
                continue
            col = int(square_match.group(1)) - 1
            row = int(square_match.group(2)) - 1
            
            type_match = re.search(r'\b([wb])([pnbrqk])\b', piece_class)
            if type_match:
                color = type_match.group(1)
                piece_type = type_match.group(2)
                piece_char = piece_type.upper() if color == 'w' else piece_type.lower()
                board[row][col] = piece_char

        fen_parts = []
        has_white_king, has_black_king = False, False
        
        for row_idx in range(7, -1, -1):
            empty_squares = 0
            row_str = ""
            for col_idx in range(8):
                piece_char = board[row_idx][col_idx]
                if piece_char:
                    if piece_char == 'K': has_white_king = True
                    if piece_char == 'k': has_black_king = True
                    if empty_squares > 0:
                        row_str += str(empty_squares)
                        empty_squares = 0
                    row_str += piece_char
                else:
                    empty_squares += 1
            if empty_squares > 0:
                row_str += str(empty_squares)
            fen_parts.append(row_str)
        
        if not has_white_king or not has_black_king:
            return None
            
        return "/".join(fen_parts)
    except Exception:
        return None


def get_stable_board_fen(driver, retries=5, delay=0.08):
    for _ in range(retries):
        try:
            animating = driver.execute_script(
                "return !!document.querySelector('.piece.moving, .piece.dragging, .piece[class*=\"moving\"], .piece[class*=\"dragging\"]');"
            )
            if animating:
                time.sleep(delay)
                continue
        except Exception:
            pass
            
        fen1 = get_board_fen(driver)
        if not fen1:
            time.sleep(delay)
            continue
            
        time.sleep(delay)
        fen2 = get_board_fen(driver)
        
        if fen1 == fen2:
            return fen1
            
    return None


def is_game_over(driver):
    try:
        script = """
        const modal = document.querySelector('.game-over-modal-container, .game-over-dialog, .game-over-modal-view');
        const btn = document.querySelector('[data-cy="game-over-modal-new-game-button"], .game-over-modal-button, button.new-game-btn');
        const gameResult = document.querySelector('.game-result, .game-over-header');
        
        const isVisible = (el) => !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));
        
        return !!((modal && isVisible(modal)) || (btn && isVisible(btn)) || (gameResult && isVisible(gameResult)));
        """
        return driver.execute_script(script)
    except Exception:
        return False


def is_player_turn(driver, player_color):
    try:
        script = """
        (function() {
            // 1. Try Move List detection (highly robust)
            const selected = document.querySelector('.node-highlight-content.selected, .selected.node-highlight-content, .node .selected');
            let lastNode = null;
            if (selected) {
                lastNode = selected.closest('.node');
            }
            if (!lastNode) {
                const moveNodes = document.querySelectorAll('.node.white-move, .node.black-move');
                if (moveNodes.length > 0) {
                    lastNode = moveNodes[moveNodes.length - 1];
                }
            }
            if (lastNode) {
                if (lastNode.classList.contains('white-move')) return 'w';
                if (lastNode.classList.contains('black-move')) return 'b';
            }

            // 2. Fallback to Highlight detection
            const highlights = document.querySelectorAll('.highlight');
            if (highlights.length === 0) return 'start';
            
            let lastMover = 'unknown';
            for (let i = 0; i < highlights.length; i++) {
                const square = highlights[i];
                const match = square.className.match(/square-(\\d+)/);
                if (!match) continue;
                const piece = document.querySelector(`.piece.${match[0]}`);
                if (piece) {
                    // Skip checked king highlights to avoid false turn positives
                    const isKing = piece.className.includes('wk') || piece.className.includes('bk');
                    if (isKing && highlights.length > 2) {
                        continue;
                    }
                    
                    let color = 'unknown';
                    const pieceClasses = piece.className.split(' ');
                    for (let c of pieceClasses) {
                        if (c.length === 2 && (c.charAt(0) === 'w' || c.charAt(0) === 'b')) {
                            color = c.charAt(0);
                            break;
                        }
                    }
                    if (color !== 'unknown') {
                        lastMover = color;
                    }
                }
            }
            return lastMover;
        })();
        """
        last_mover = driver.execute_script(script)
        if last_mover == 'start':
            return player_color == 'w'
        if last_mover == 'unknown':
            return False
        return last_mover != player_color
    except Exception:
        return False


def detect_player_color(driver):
    try:
        is_flipped = driver.execute_script("""
            const board = document.querySelector('chess-board, wc-chess-board, .board');
            if (!board) return null;
            return board.classList.contains('flipped') || board.className.includes('flipped');
        """)
        if is_flipped is True:
            return 'b'
        elif is_flipped is False:
            position = driver.execute_script("""
                const coordinate_elements = Array.from(document.querySelectorAll('.coordinate-light, text.coordinate'));
                const rank_one = coordinate_elements.find(el => el.textContent.trim() === '1');
                if (!rank_one) return 'unk';
                return rank_one.getBoundingClientRect().top > (window.innerHeight/2) ? 'bottom' : 'top';
            """)
            if position == 'top':
                return 'b'
            elif position == 'bottom':
                return 'w'
        return 'unk'
    except Exception:
        return 'unk'


def get_opponent_elo(driver):
    try:
        text = driver.execute_script("const top_panel = document.querySelector('.player-top, .player-component.player-top, .player-component.top, .board-layout-top'); return top_panel ? top_panel.innerText : '';")
        numbers = re.findall(r'\d+', str(text))
        for num in numbers:
            value = int(num)
            if 100 <= value <= 3500:
                return value
        return 1500
    except Exception:
        return 1500
