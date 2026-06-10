import subprocess
import logging
from config import STOCKFISH_PATH, LC0_PATH

logger = logging.getLogger("analyzer")

class UCIEngine:
    def __init__(self, command_args):
        self.args = command_args
        self.process = None

    def start(self):
        try:
            self.process = subprocess.Popen(
                self.args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                bufsize=1
            )
            self.send("uci")
            # Consume startup response until uciok
            while True:
                line = self.read_line()
                if line is None or line == "uciok":
                    break
        except Exception as e:
            logger.error(f"Engine failed to start {self.args[0]}: {e}")

    def send(self, command):
        if self.process and self.process.stdin:
            try:
                self.process.stdin.write(command + "\n")
                self.process.stdin.flush()
            except Exception:
                pass

    def read_line(self):
        if self.process and self.process.stdout:
            try:
                line = self.process.stdout.readline()
                if line == "":  # EOF (process died)
                    return None
                return line.strip()
            except Exception:
                pass
        return None

    def stop(self):
        if self.process:
            self.process.terminate()

    def is_alive(self):
        return self.process and self.process.poll() is None


class Stockfish(UCIEngine):
    def __init__(self):
        super().__init__([STOCKFISH_PATH])

    def get_best_move(self, fen, color, depth=15):
        if not self.is_alive():
            self.start()
        self.send(f"position fen {fen} {color} - - 0 1")
        self.send(f"go depth {depth}")
        
        while True:
            line = self.read_line()
            if line is None:  # EOF
                break
            if not line:  # Skip empty line
                continue
            if line.startswith("bestmove"):
                parts = line.split()
                if len(parts) > 1:
                    return parts[1]
                break
        return None


class Maia(UCIEngine):
    def __init__(self, weight_file):
        super().__init__([LC0_PATH, f"--weights={weight_file}"])

    def get_top_moves(self, fen, color, nodes=100):
        if not self.is_alive():
            self.start()
        self.send(f"position fen {fen} {color} - - 0 1")
        self.send("setoption name MultiPV value 3")
        self.send(f"go nodes {nodes}")
        
        moves = []
        while True:
            line = self.read_line()
            if line is None:  # EOF
                break
            if not line:  # Skip empty line
                continue
            if line.startswith("bestmove"):
                if not moves and len(line.split()) > 1:
                    moves.append(line.split()[1])
                break
            if line.startswith("info") and "pv" in line:
                try:
                    parts = line.split()
                    pv_idx = parts.index("pv")
                    move = parts[pv_idx + 1]
                    if move not in moves:
                        moves.append(move)
                except Exception:
                    pass
        return moves[:3]
