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


def main():
    driver = inject_driver()
    print(">>> Browser connected.")
    
    stockfish_engine = StockfishEngine()
    
    current_maia_engine = None
    player_color = 'w'
    opponent_elo = 1500
    
    last_fen = "start"
    game_is_active = True
    
    print(">>> Starting game...")
    time.sleep(2)
    player_color = get_side_robust(driver)
    opponent_elo = get_elo_robust(driver)
    
    available_models = [1100, 1200, 1300, 1400, 1500, 1600, 1700, 1800, 1900]
    model_elo = min(available_models, key=lambda x: abs(x - opponent_elo))
    current_maia_engine = MaiaEngine(f"maia/maia-{model_elo}.pb.gz")
    print(f"I: Color: {player_color}, Opponent: {opponent_elo}, Model: Maia-{model_elo}")

    while True:
        try:
            if is_game_over(driver):
                if game_is_active:
                    print(">>> GAME OVER. Waiting for new game...")
                    clear_overlay(driver)
                    game_is_active = False
                time.sleep(2)
                continue
            
            if not game_is_active:
                print(">>> NEW GAME DETECTED!")
                time.sleep(2)
                player_color = get_side_robust(driver)
                opponent_elo = get_elo_robust(driver)
                model_elo = min(available_models, key=lambda x: abs(x - opponent_elo))
                
                if current_maia_engine: current_maia_engine.stop()
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