import time
import subprocess
import random
import re
import json
import threading
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By


FILES = "abcdefgh"
RANKS = "12345678"


class EngineProcess:
    def __init__(self, command_args):
        self.command_args = command_args
        self.process = None

    def start(self):
        try:
            self.process = subprocess.Popen(
                self.command_args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                bufsize=1
            )
            self.send_command("uci")
        except Exception as e:
            print(f"({self.command_args[0]}): {e}")

    def send_command(self, message):
        if self.process and self.process.stdin:
            try:
                self.process.stdin.write(message + "\n")
                self.process.stdin.flush()
            except: pass

    def stop(self):
        if self.process:
            self.process.terminate()

    def is_alive(self):
        return self.process and self.process.poll() is None

class StockfishEngine(EngineProcess):

    def __init__(self, exe_path="stockfish.exe"):
        super().__init__([exe_path])

    def reset(self):
        if not self.is_alive():
            return
        self.send_command("ucinewgame")

    def get_best_move(self, fen, color):
        if not self.is_alive(): self.start()
        

        full_fen = f"{fen} {color} - - 0 1"
        self.send_command(f"position fen {full_fen}")
        self.send_command("go depth 15")
        
        best_move = None
        while True:
            line = self.process.stdout.readline()
            if not line: break
            line = line.strip()
            if line.startswith("bestmove"):
                parts = line.split()
                if len(parts) > 1:
                    best_move = parts[1]
                break
        return best_move

class MaiaEngine(EngineProcess):
    def __init__(self, weight_file="maia/maia-1500.pb.gz"):
        super().__init__(["lc0.exe", f"--weights={weight_file}"])

    def get_human_moves(self, fen, color):
        if not self.is_alive(): self.start()

        full_fen = f"{fen} {color} - - 0 1"
        self.send_command(f"position fen {full_fen}")
        self.send_command("setoption name MultiPV value 3")
        self.send_command("go nodes 100") 
        
        moves = []
        while True:
            line = self.process.stdout.readline()
            if not line: break
            line = line.strip()
            
            if line.startswith("bestmove"):
                if not moves and len(line.split()) > 1:
                     moves.append(line.split()[1])
                break
            
            if line.startswith("info") and "pv" in line:
                try:
                    parts = line.split()
                    pv_idx = parts.index("pv")
                    move = parts[pv_idx+1]
                    if move not in moves:
                        moves.append(move)
                except: pass
        
        return moves[:3]

class AnalysisEngine:
    def __init__(self):
        self.last_fen = None

    def reset(self):
        self.last_fen = None

    def get_control_squares(self, fen):
        board = parse_fen_board(fen)
        control = {"w": set(), "b": set()}
        for (file_idx, rank_idx), piece in board.items():
            color = "w" if piece.isupper() else "b"
            piece_type = piece.lower()
            control[color].update(get_piece_attacks(board, file_idx, rank_idx, piece_type, color))
        return control

    def render(self, driver, fen, player_color, arrows):
        if not fen or fen == self.last_fen:
            return
        control = self.get_control_squares(fen)
        self.last_fen = fen
        draw_analysis(driver, control, player_color, arrows)


def parse_fen_board(fen):
    rows = fen.split()[0].split("/")
    board = {}
    for rank_idx, row in enumerate(reversed(rows)):
        file_idx = 0
        for ch in row:
            if ch.isdigit():
                file_idx += int(ch)
            else:
                board[(file_idx, rank_idx)] = ch
                file_idx += 1
    return board


def get_piece_attacks(board, file_idx, rank_idx, piece_type, color):
    attacks = set()
    directions = []
    if piece_type == "p":
        step = 1 if color == "w" else -1
        for dx in (-1, 1):
            tx, ty = file_idx + dx, rank_idx + step
            if 0 <= tx <= 7 and 0 <= ty <= 7:
                attacks.add((tx, ty))
        return attacks
    if piece_type == "n":
        jumps = [(1, 2), (2, 1), (-1, 2), (-2, 1), (1, -2), (2, -1), (-1, -2), (-2, -1)]
        for dx, dy in jumps:
            tx, ty = file_idx + dx, rank_idx + dy
            if 0 <= tx <= 7 and 0 <= ty <= 7:
                attacks.add((tx, ty))
        return attacks
    if piece_type == "b":
        directions = [(1, 1), (1, -1), (-1, 1), (-1, -1)]
    if piece_type == "r":
        directions = [(1, 0), (-1, 0), (0, 1), (0, -1)]
    if piece_type == "q":
        directions = [(1, 1), (1, -1), (-1, 1), (-1, -1), (1, 0), (-1, 0), (0, 1), (0, -1)]
    if piece_type == "k":
        directions = [(1, 1), (1, -1), (-1, 1), (-1, -1), (1, 0), (-1, 0), (0, 1), (0, -1)]
        for dx, dy in directions:
            tx, ty = file_idx + dx, rank_idx + dy
            if 0 <= tx <= 7 and 0 <= ty <= 7:
                attacks.add((tx, ty))
        return attacks
    for dx, dy in directions:
        tx, ty = file_idx + dx, rank_idx + dy
        while 0 <= tx <= 7 and 0 <= ty <= 7:
            attacks.add((tx, ty))
            if (tx, ty) in board:
                break
            tx += dx
            ty += dy
    return attacks

def inject_driver():
    options = Options()
    options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
    return webdriver.Chrome(options=options)

def get_fen_from_dom(driver):
    pieces = driver.find_elements(By.CSS_SELECTOR, "div.piece")
    board = [[None]*8 for _ in range(8)]
    
    for piece in pieces:
        piece_class = piece.get_attribute("class")
        square_match = re.search(r'square-(\d)(\d)', piece_class)
        if not square_match: continue
        column = int(square_match.group(1)) - 1
        row = int(square_match.group(2)) - 1
        
        type_match = re.search(r'\b([wb])([pnbrqk])\b', piece_class)
        if type_match:
            color = type_match.group(1)
            piece_type = type_match.group(2)
            piece_char = piece_type.upper() if color == 'w' else piece_type.lower()
            board[row][column] = piece_char

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
        if empty_squares > 0: row_str += str(empty_squares)
        fen_parts.append(row_str)
    
    if not has_white_king or not has_black_king:
        return None
        
    return "/".join(fen_parts)

def is_game_over(driver):
    try:

        script = """
            const modal = document.querySelector('.game-over-modal-container');
            const btn = document.querySelector('[data-cy="game-over-modal-new-game-button"]');
            return !!(modal || btn);
        """
        return driver.execute_script(script)
    except:
        return False

def check_turn(driver, player_color):
    try:
        script = """
        (function() {
            const highlights = document.querySelectorAll('.highlight');
            if (highlights.length === 0) return 'start';
            
            for (let square of highlights) {
                const match = square.className.match(/square-(\\d+)/);
                if (!match) continue;
                const piece = document.querySelector(`.piece.${match[0]}`);
                if (piece) {
                    if (piece.className.includes('w')) return 'w';
                    if (piece.className.includes('b')) return 'b';
                    if (piece.className.match(/w[pnbrqk]/)) return 'w';
                    return 'b';
                }
            }
            return 'unknown';
        })();
        """
        last_mover = driver.execute_script(script)
        
        if last_mover == 'start': return (player_color == 'w')
        if last_mover == 'unknown': return False
        
        return last_mover != player_color
    except:
        return False

def get_side_robust(driver):
    try:
        script_check_bottom = """
            (function() {
                const board = document.querySelector('chess-board') || document.querySelector('wc-chess-board');
                if (!board) return 'unk';
                const rect = board.getBoundingClientRect();
                const pieces = Array.from(document.querySelectorAll('.piece'));
                const bottom_limit = rect.top + rect.height * 0.75;
                let w = 0;
                let b = 0;
                for (const piece of pieces) {
                    const pr = piece.getBoundingClientRect();
                    const center_y = pr.top + pr.height / 2;
                    if (center_y >= bottom_limit) {
                        if (piece.className.includes('w')) w += 1;
                        if (piece.className.includes('b')) b += 1;
                    }
                }
                if (w + b < 2) return 'unk';
                return w >= b ? 'w' : 'b';
            })();
        """
        bottom_color = driver.execute_script(script_check_bottom)
        if bottom_color in ("w", "b"):
            print(f"LOG: Side is {'White' if bottom_color == 'w' else 'Black'} (Bottom pieces)")
            return bottom_color

        script_check_class = "const board = document.querySelector('chess-board') || document.querySelector('wc-chess-board'); return board && board.classList.contains('flipped');"
        if driver.execute_script(script_check_class):
            print("LOG: Side is Black (Class detection)")
            return 'b'

        script_check_coordinates = """
            const coordinate_elements = Array.from(document.querySelectorAll('.coordinate-light, text.coordinate'));
            const rank_one = coordinate_elements.find(el => el.textContent.trim() === '1');
            if (!rank_one) return 'unk';
            return rank_one.getBoundingClientRect().top > (window.innerHeight/2) ? 'bottom' : 'top';
        """
        position = driver.execute_script(script_check_coordinates)
        if position == 'top':
            print("LOG: Side is Black (Coordinate detection)")
            return 'b'

        print("LOG: Side is White")
        return 'w'
    except:
        return 'w'

def get_elo_robust(driver):
    try:
        script = """
        (function() {
            const top_panel = document.querySelector('.player-component.top');
            if (!top_panel) return 1500;
            return top_panel.innerText;
        })();
        """
        text = driver.execute_script(script)
        numbers = re.findall(r'\d+', str(text))
        for number in numbers:
            value = int(number)
            if 100 <= value <= 3500: return value
        return 1500
    except: return 1500


def clear_overlay(driver):
    driver.execute_script("const o=document.getElementById('ai-overlay'); if(o) o.remove();")
    driver.execute_script("const a=document.getElementById('ai-analysis'); if(a) a.remove();")

def is_game_started(driver):
    try:
        script = """
            (function() {
                const clocks = Array.from(document.querySelectorAll('.clock-component, .clock, .clock-container, [data-cy="clock"], [class*="clock"]'))
                    .filter(el => el.offsetParent !== null);
                if (clocks.length > 0) return true;

                const moves = document.querySelectorAll('.move-text, .move, .move-node, .notation-notation');
                if (moves.length > 0) return true;

                return false;
            })();
        """
        return driver.execute_script(script)
    except:
        return False

def draw_moves(driver, maia_moves, stockfish_move, is_black):
    moves_data = []
    
    move_colors = ["#f44336", "#ff9800", "#ffeb3b"]
    for index, move in enumerate(maia_moves):
        if index >= 3: break
        moves_data.append({
            "from_square": move[:2], 
            "to_square": move[2:4], 
            "color": move_colors[index], 
            "type": "maia", 
            "opacity": 0.9 if index == 0 else 0.6
        })

    if stockfish_move:
        moves_data.append({
            "from_square": stockfish_move[:2], 
            "to_square": stockfish_move[2:4], 
            "color": "#00e676", 
            "type": "sf", 
            "opacity": 1.0
        })

    data_json = json.dumps(moves_data)
    is_flipped_js = "true" if is_black else "false"

    script = f"""
    (function() {{
        const board = document.querySelector('chess-board') || document.querySelector('wc-chess-board');
        const any_piece = document.querySelector('.piece');
        const target = board || (any_piece ? any_piece.parentElement : document.body);
        const rect = target.getBoundingClientRect();
        let overlay = document.getElementById('ai-overlay');
        if (overlay) overlay.remove();
        
        overlay = document.createElement('div');
        overlay.id = 'ai-overlay';
        Object.assign(overlay.style, {{
            position: 'absolute', top: (rect.top + window.scrollY) + 'px', left: (rect.left + window.scrollX) + 'px',
            width: rect.width + 'px', height: rect.height + 'px', pointerEvents: 'none', zIndex: '9999'
        }});
        document.body.appendChild(overlay);

        const is_flipped = {is_flipped_js};
        const moves = {data_json};

        function get_position(square) {{
            const files = 'abcdefgh';
            const ranks = '12345678';
            let file_index = files.indexOf(square[0]);
            let rank_index = ranks.indexOf(square[1]);
            
            let x_pos, y_pos;
            if (is_flipped) {{
                x_pos = (7 - file_index) * 12.5;
                y_pos = rank_index * 12.5;
            }} else {{
                x_pos = file_index * 12.5;
                y_pos = (7 - rank_index) * 12.5;
            }}
            return {{ x: x_pos + 6.25, y: y_pos + 6.25 }};
        }}

        const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        svg.setAttribute("viewBox", "0 0 100 100");
        svg.style.width = "100%"; svg.style.height = "100%";

        moves.filter(m => m.type === 'maia').forEach(m => {{
            const start = get_position(m.from_square);
            const end = get_position(m.to_square);
            
            const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
            line.setAttribute("x1", start.x); line.setAttribute("y1", start.y);
            line.setAttribute("x2", end.x); line.setAttribute("y2", end.y);
            line.setAttribute("stroke", m.color);
            line.setAttribute("stroke-width", "0.6");
            line.style.opacity = m.opacity;
            svg.appendChild(line);
            
            const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
            circle.setAttribute("cx", end.x); circle.setAttribute("cy", end.y);
            circle.setAttribute("r", "3");
            circle.setAttribute("fill", "none");
            circle.setAttribute("stroke", m.color);
            circle.setAttribute("stroke-width", "0.8");
            svg.appendChild(circle);
        }});

        moves.filter(m => m.type === 'sf').forEach(m => {{
            const start = get_position(m.from_square);
            const end = get_position(m.to_square);
            
            const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
            line.setAttribute("x1", start.x); line.setAttribute("y1", start.y);
            line.setAttribute("x2", end.x); line.setAttribute("y2", end.y);
            line.setAttribute("stroke", m.color);
            line.setAttribute("stroke-width", "1.2");
            line.setAttribute("stroke-linecap", "round");
            svg.appendChild(line);
            
            const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
            circle.setAttribute("cx", end.x); circle.setAttribute("cy", end.y);
            circle.setAttribute("r", "2.5");
            circle.setAttribute("fill", m.color);
            svg.appendChild(circle);
        }});

        overlay.appendChild(svg);
    }})();
    """
    driver.execute_script(script)

def draw_analysis(driver, control, player_color, arrows):
    friendly = "w" if player_color == "w" else "b"
    enemy = "b" if player_color == "w" else "w"
    friendly_squares = control.get(friendly, set())
    enemy_squares = control.get(enemy, set())

    squares_payload = {
        "friendly": [f"{file_idx}{rank_idx}" for file_idx, rank_idx in friendly_squares],
        "enemy": [f"{file_idx}{rank_idx}" for file_idx, rank_idx in enemy_squares]
    }
    payload = json.dumps(squares_payload)
    arrows_json = json.dumps(arrows)
    is_flipped_js = "true" if player_color == "b" else "false"

    script = f"""
    (function() {{
        const board = document.querySelector('chess-board') || document.querySelector('wc-chess-board');
        if (!board) return;
        let container = document.getElementById('ai-analysis');
        if (container) container.remove();
        container = document.createElement('div');
        container.id = 'ai-analysis';
        container.style.position = 'absolute';
        container.style.top = '0';
        container.style.left = '0';
        container.style.right = '0';
        container.style.bottom = '0';
        container.style.pointerEvents = 'none';
        container.style.zIndex = '9998';
        board.appendChild(container);

        const squares = {payload};
        const addSquare = (classSuffix, color) => {{
            const el = document.createElement('div');
            el.className = `highlight square-${{classSuffix}}`;
            el.style.background = color;
            container.appendChild(el);
        }};

        squares.friendly.forEach(sq => {{
            const x = parseInt(sq[0], 10) + 1;
            const y = parseInt(sq[1], 10) + 1;
            addSquare(`${{x}}${{y}}`, 'rgba(33, 150, 243, 0.5)');
        }});
        squares.enemy.forEach(sq => {{
            const x = parseInt(sq[0], 10) + 1;
            const y = parseInt(sq[1], 10) + 1;
            addSquare(`${{x}}${{y}}`, 'rgba(235, 97, 80, 0.8)');
        }});

        if (!arrows || arrows.length === 0) return;
        const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        svg.setAttribute("viewBox", "0 0 100 100");
        svg.style.width = "100%";
        svg.style.height = "100%";
        svg.style.position = "absolute";
        svg.style.top = "0";
        svg.style.left = "0";
        container.appendChild(svg);

        const files = 'abcdefgh';
        const ranks = '12345678';
        const is_flipped = {is_flipped_js};
        const getPos = (square) => {{
            const fileIndex = files.indexOf(square[0]);
            const rankIndex = ranks.indexOf(square[1]);
            if (is_flipped) {{
                return {{ x: (7 - fileIndex) * 12.5 + 6.25, y: rankIndex * 12.5 + 6.25 }};
            }}
            return {{ x: fileIndex * 12.5 + 6.25, y: (7 - rankIndex) * 12.5 + 6.25 }};
        }};

        const arrowWidth = 4;
        const headLength = 6;
        const arrowsData = {arrows_json};
        arrowsData.forEach(arrow => {{
            const start = getPos(arrow.from);
            const end = getPos(arrow.to);
            const dx = end.x - start.x;
            const dy = end.y - start.y;
            const len = Math.hypot(dx, dy);
            if (len < 0.1) return;
            const ux = dx / len;
            const uy = dy / len;
            const perpX = -uy;
            const perpY = ux;
            const tailX = end.x - ux * headLength;
            const tailY = end.y - uy * headLength;
            const p1 = `${{start.x + perpX * arrowWidth}},${{start.y + perpY * arrowWidth}}`;
            const p2 = `${{tailX + perpX * arrowWidth}},${{tailY + perpY * arrowWidth}}`;
            const p3 = `${{tailX + perpX * (arrowWidth * 2)}},${{tailY + perpY * (arrowWidth * 2)}}`;
            const p4 = `${{end.x}},${{end.y}}`;
            const p5 = `${{tailX - perpX * (arrowWidth * 2)}},${{tailY - perpY * (arrowWidth * 2)}}`;
            const p6 = `${{tailX - perpX * arrowWidth}},${{tailY - perpY * arrowWidth}}`;
            const p7 = `${{start.x - perpX * arrowWidth}},${{start.y - perpY * arrowWidth}}`;
            const polygon = document.createElementNS("http://www.w3.org/2000/svg", "polygon");
            polygon.setAttribute("class", "arrow");
            polygon.setAttribute("points", [p1, p2, p3, p4, p5, p6, p7].join(" "));
            polygon.setAttribute("fill", arrow.color || "#00e676");
            polygon.setAttribute("opacity", "0.85");
            svg.appendChild(polygon);
        }});
    }})();
    """
    driver.execute_script(script)

def get_best_arrows(stockfish_move):
    if not stockfish_move or len(stockfish_move) < 4:
        return []
    return [{"from": stockfish_move[:2], "to": stockfish_move[2:4], "color": "#00e676"}]

def main():
    driver = inject_driver()
    print(">>> Browser connected.")
    
    stockfish_engine = StockfishEngine()
    analysis_engine = AnalysisEngine()
    
    current_maia_engine = None
    player_color = 'w'
    opponent_elo = 1500
    
    last_fen = "start"
    game_is_active = False
    
    print(">>> Starting game...")
    time.sleep(2)
    
    available_models = [1100, 1200, 1300, 1400, 1500, 1600, 1700, 1800, 1900]
    model_elo = min(available_models, key=lambda x: abs(x - opponent_elo))

    def reset_game_state():
        nonlocal current_maia_engine, last_fen, game_is_active
        clear_overlay(driver)
        if current_maia_engine:
            current_maia_engine.stop()
            current_maia_engine = None
        stockfish_engine.reset()
        analysis_engine.reset()
        last_fen = "reset"
        game_is_active = False

    while True:
        try:
            if is_game_over(driver):
                if game_is_active:
                    print(">>> GAME OVER. Waiting for new game...")
                    reset_game_state()
                time.sleep(2)
                continue

            if not is_game_started(driver):
                if game_is_active:
                    print(">>> GAME PAUSED/LOBBY. Resetting state...")
                    reset_game_state()
                time.sleep(1)
                continue

            if not game_is_active:
                print(">>> NEW GAME DETECTED!")
                time.sleep(1)
                player_color = get_side_robust(driver)
                opponent_elo = get_elo_robust(driver)
                model_elo = min(available_models, key=lambda x: abs(x - opponent_elo))
                
                current_maia_engine = MaiaEngine(f"maia/maia-{model_elo}.pb.gz")
                
                print(f"I: New settings -> Color: {player_color}, Elo: {opponent_elo}")
                game_is_active = True
                last_fen = "reset"
            
            is_my_turn = check_turn(driver, player_color)
            
            if is_my_turn:
                time.sleep(0.2)
                current_fen = get_fen_from_dom(driver)
                
                if current_fen and current_fen != last_fen:
                    print(f"A: My turn! Analyzing... ({current_fen[:15]}...)")
                    
                    human_moves = current_maia_engine.get_human_moves(current_fen, player_color)
                    best_engine_move = stockfish_engine.get_best_move(current_fen, player_color)
                    
                    if len(human_moves) > 1 and random.random() < 0.15:
                        print("DBG: Human error simulation -> hiding best maia move.")
                        human_moves.pop(0)

                    print(f"OUT: Maia: {human_moves}, SF: {best_engine_move}")
                    
                    draw_moves(driver, human_moves, best_engine_move, player_color == 'b')
                    analysis_engine.render(
                        driver,
                        current_fen,
                        player_color,
                        get_best_arrows(best_engine_move)
                    )
                    last_fen = current_fen
                elif current_fen is None:
                    time.sleep(0.5)
            else:
                clear_overlay(driver)
                last_fen = "waiting"
                time.sleep(0.5)
                
            time.sleep(0.1)

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"ERR: {e}")
            time.sleep(1)


if __name__ == "__main__":
    main()
