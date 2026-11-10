"""Chess engine verification: perft node counts (known published values) + rules checks. Run: python test_chess.py"""
import sys, time
from chess import Position, outcome, perft, START_FEN

ok = bad = 0
def check(n, c):
    global ok, bad
    if c: ok += 1
    else: bad += 1; print("FAIL", n)

PERFT = [
    ("start", START_FEN, [20, 400, 8902, 197281]),
    ("kiwipete", "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1", [48, 2039, 97862]),
    ("pos3", "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1", [14, 191, 2812, 43238]),
    ("pos4", "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1", [6, 264, 9467]),
    ("pos4m", "r2q1rk1/pP1p2pp/Q4n2/bbp1p3/Np6/1B3NBn/pPPP1PPP/R3K2R b KQ - 0 1", [6, 264, 9467]),
    ("pos5", "rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8", [44, 1486, 62379]),
    ("pos6", "r4rk1/1pp1qppp/p1np1n2/2b1p1B1/2B1P1b1/P1NP1N2/1PP1QPPP/R4RK1 w - - 0 10", [46, 2079, 89890]),
]
t0 = time.time()
for name, fen, counts in PERFT:
    p = Position.from_fen(fen)
    for d, want in enumerate(counts, 1):
        got = perft(p, d)
        check(f"perft {name} d{d}: {got} == {want}", got == want)
print("perft time %.1fs" % (time.time() - t0))

# FEN round trip
for _, fen, _c in PERFT:
    check("fen roundtrip", Position.from_fen(fen).fen() == fen)

def play(moves):
    p = Position.start(); keys = [p.key()]; sans = []
    for u in moves:
        m = p.parse_uci(u); assert m, u
        sans.append(p.san(m)); p = p.make(m); keys.append(p.key())
    return p, keys, sans

p, k, s = play(["f2f3", "e7e5", "g2g4", "d8h4"])
check("fool's mate", outcome(p, k) == ("0-1", "checkmate") and s[-1] == "Qh4#")
p, k, s = play(["e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "g8f6", "e1g1"])
check("castle O-O san + rook moved", s[-1] == "O-O" and p.b[5] == "R" and p.b[6] == "K")
# en passant
p, k, s = play(["e2e4", "a7a6", "e4e5", "d7d5", "e5d6"])
check("en passant removes pawn", p.b[35] == "." and p.b[43] == "P" and s[-1] == "exd6")
# promotion san
p = Position.from_fen("8/P6k/8/8/8/8/8/K7 w - - 0 1")
m = p.parse_uci("a7a8q"); check("promotion", m and p.san(m) == "a8=Q" and p.make(m).b[56] == "Q")
check("promotion needs piece", p.parse_uci("a7a8") is None and p.parse_uci("a7a8k") is None)
# illegal / garbage
st = Position.start()
for bad_m in ("e2e5", "e1e2", "a1a3", "", "zz", "e2e4q", 5, None, "e2e4\n", "E2E4 "):
    check(f"reject {bad_m!r}", st.parse_uci(bad_m) is None)
# cannot castle through check / out of check / after rook moved
p = Position.from_fen("r3k2r/8/5q2/8/8/8/8/R3K2R w KQkq - 0 1")
check("no castling through attacked square", p.parse_uci("e1g1") is None and p.parse_uci("e1c1") is not None)
p = Position.from_fen("r3k2r/8/8/8/4q3/8/8/R3K2R w KQkq - 0 1")
check("no castling out of check", p.parse_uci("e1g1") is None and p.parse_uci("e1c1") is None)
# pinned piece
p = Position.from_fen("4k3/4r3/8/8/8/8/4N3/4K3 w - - 0 1")
check("pinned knight cannot move", not [m for m in p.legal_moves() if m[0] == 12])
# stalemate / insufficient / 50 / repetition
p = Position.from_fen("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")
check("stalemate", outcome(p, [p.key()]) == ("1/2-1/2", "stalemate"))
for fen in ("8/8/8/4k3/8/8/8/4K3 w - - 0 1", "8/8/8/4k3/8/8/8/3BK3 w - - 0 1", "8/8/8/4k3/8/8/8/3NK3 w - - 0 1",
            "1kb5/8/8/8/8/8/8/3BK3 w - - 0 1"):
    p = Position.from_fen(fen); check("insufficient " + fen, outcome(p, [p.key()]) == ("1/2-1/2", "insufficient"))
for fen in ("8/8/8/4k3/8/8/4P3/4K3 w - - 0 1", "8/8/8/4k3/8/8/8/2BBK3 w - - 0 1", "4kb2/8/8/8/8/8/8/3BK3 w - - 0 1"):
    p = Position.from_fen(fen); check("sufficient " + fen, outcome(p, [p.key()]) is None)
p = Position.from_fen("8/8/8/4k3/8/8/8/R3K3 w - - 100 80")
check("fifty-move", outcome(p, [p.key()]) == ("1/2-1/2", "fifty"))
p, k, s = play(["g1f3", "g8f6", "f3g1", "f6g8"] * 2)
check("threefold repetition", outcome(p, k) == ("1/2-1/2", "repetition"))
p, k, s = play(["g1f3", "g8f6", "f3g1", "f6g8"])
check("twofold is not a draw", outcome(p, k) is None)
# SAN disambiguation
p = Position.from_fen("4k3/8/8/8/8/8/7K/R5R1 w - - 0 1")
check("san disambiguation", p.san(p.parse_uci("a1d1")) == "Rad1" and p.san(p.parse_uci("g1d1")) == "Rgd1")
p = Position.from_fen("4k3/8/8/R7/8/8/8/R3K3 w - - 0 1")
check("san rank disambiguation", p.san(p.parse_uci("a1a3")) == "R1a3" and p.san(p.parse_uci("a5a3")) == "R5a3")
print(f"chess: {ok} ok, {bad} failed")
sys.exit(1 if bad else 0)
