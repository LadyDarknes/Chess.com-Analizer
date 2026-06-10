import json

def setup_f4_listener(driver):
    try:
        driver.execute_script("""
        if (window.showOverlay === undefined) {
            window.showOverlay = true;
        }
        if (!window.hasF4Listener) {
            window.hasF4Listener = true;
            window.addEventListener('keydown', function(e) {
                if (e.key === 'F4') {
                    window.showOverlay = !window.showOverlay;
                    const overlay = document.getElementById('ai-overlay');
                    if (overlay) {
                        overlay.style.display = window.showOverlay ? 'block' : 'none';
                    }
                }
            });
        }
        """)
    except Exception:
        pass


def clear_overlay(driver):
    try:
        driver.execute_script("const o=document.getElementById('ai-overlay'); if(o) o.remove();")
    except Exception:
        pass


def draw_moves(driver, maia_moves, stockfish_move, is_black):
    setup_f4_listener(driver)
    
    moves_data = []
    move_colors = ["#ff007f", "#ffaa00", "#b000ff"]
    
    for idx, move in enumerate(maia_moves[:3]):
        moves_data.append({
            "from_square": move[:2],
            "to_square": move[2:4],
            "color": move_colors[idx],
            "type": "maia",
            "opacity": 0.9 if idx == 0 else 0.6
        })

    if stockfish_move:
        moves_data.append({
            "from_square": stockfish_move[:2],
            "to_square": stockfish_move[2:4],
            "color": "#00f3ff",
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
            position: 'absolute',
            top: (rect.top + window.scrollY) + 'px',
            left: (rect.left + window.scrollX) + 'px',
            width: rect.width + 'px',
            height: rect.height + 'px',
            pointerEvents: 'none',
            zIndex: '9999',
            display: window.showOverlay ? 'block' : 'none'
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
        svg.style.width = "100%";
        svg.style.height = "100%";

        function draw_arrow(start, end, color, width, opacity) {{
            const dx = end.x - start.x;
            const dy = end.y - start.y;
            const len = Math.hypot(dx, dy);
            if (len > 0) {{
                const u = {{ x: dx / len, y: dy / len }};
                const v = {{ x: -u.y, y: u.x }};
                
                const arrowLength = 3.5;
                const arrowWidth = 2.0;
                
                const tip = end;
                const base = {{ x: end.x - u.x * arrowLength, y: end.y - u.y * arrowLength }};
                const left = {{ x: base.x + v.x * arrowWidth, y: base.y + v.y * arrowWidth }};
                const right = {{ x: base.x - v.x * arrowWidth, y: base.y - v.y * arrowWidth }};
                
                // Starting dot
                const dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
                dot.setAttribute("cx", start.x);
                dot.setAttribute("cy", start.y);
                dot.setAttribute("r", (width * 1.0).toString());
                dot.setAttribute("fill", color);
                dot.style.opacity = (opacity * 0.9).toString();
                svg.appendChild(dot);
                
                // Glow line (thick, low opacity)
                const glowLine = document.createElementNS("http://www.w3.org/2000/svg", "line");
                glowLine.setAttribute("x1", start.x);
                glowLine.setAttribute("y1", start.y);
                glowLine.setAttribute("x2", base.x);
                glowLine.setAttribute("y2", base.y);
                glowLine.setAttribute("stroke", color);
                glowLine.setAttribute("stroke-width", (width * 3.0).toString());
                glowLine.style.opacity = (opacity * 0.25).toString();
                svg.appendChild(glowLine);
                
                // Core line
                const coreLine = document.createElementNS("http://www.w3.org/2000/svg", "line");
                coreLine.setAttribute("x1", start.x);
                coreLine.setAttribute("y1", start.y);
                coreLine.setAttribute("x2", base.x);
                coreLine.setAttribute("y2", base.y);
                coreLine.setAttribute("stroke", color);
                coreLine.setAttribute("stroke-width", width.toString());
                coreLine.style.opacity = opacity.toString();
                svg.appendChild(coreLine);
                
                // Arrowhead glow
                const glowArrow = document.createElementNS("http://www.w3.org/2000/svg", "polygon");
                const glowBase = {{ x: end.x - u.x * (arrowLength * 1.2), y: end.y - u.y * (arrowLength * 1.2) }};
                const glowLeft = {{ x: glowBase.x + v.x * (arrowWidth * 1.3), y: glowBase.y + v.y * (arrowWidth * 1.3) }};
                const glowRight = {{ x: glowBase.x - v.x * (arrowWidth * 1.3), y: glowBase.y - v.y * (arrowWidth * 1.3) }};
                glowArrow.setAttribute("points", tip.x + "," + tip.y + " " + glowLeft.x + "," + glowLeft.y + " " + glowRight.x + "," + glowRight.y);
                glowArrow.setAttribute("fill", color);
                glowArrow.style.opacity = (opacity * 0.25).toString();
                svg.appendChild(glowArrow);

                // Arrowhead core
                const coreArrow = document.createElementNS("http://www.w3.org/2000/svg", "polygon");
                coreArrow.setAttribute("points", tip.x + "," + tip.y + " " + left.x + "," + left.y + " " + right.x + "," + right.y);
                coreArrow.setAttribute("fill", color);
                coreArrow.style.opacity = opacity.toString();
                svg.appendChild(coreArrow);
            }}
        }}

        // Draw Maia moves first (underneath)
        moves.filter(m => m.type === 'maia').forEach(m => {{
            const start = get_position(m.from_square);
            const end = get_position(m.to_square);
            draw_arrow(start, end, m.color, 0.8, m.opacity);
        }});

        // Draw Stockfish moves on top
        moves.filter(m => m.type === 'sf').forEach(m => {{
            const start = get_position(m.from_square);
            const end = get_position(m.to_square);
            draw_arrow(start, end, m.color, 1.3, m.opacity);
        }});

        overlay.appendChild(svg);
    }})();
    """
    try:
        driver.execute_script(script)
    except Exception:
        pass
