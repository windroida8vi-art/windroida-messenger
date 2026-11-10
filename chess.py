"""Chess rules engine (pure Python, no dependencies). The SERVER is the only judge of a game: every move a client
sends is checked against `Position.legal_moves()`. Squares are 0..63 with a1=0, h1=7, a8=56, h8=63.

    p = Position.start();  p.legal_moves() -> [(frm, to, promo), ...]   (promo: '' or one of 'q','r','b','n')
    p2 = p.make(move);     p.san(move) -> 'Nf3', 'exd5', 'O-O', 'e8=Q+' ...
    outcome(p, history_keys) -> None | ('1-0'|'0-1'|'1/2-1/2', reason)

Verified with perft (known node counts) in test_chess.py.
"""

FILES = "abcdefgh"
START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def sq_name(s):
    return FILES[s & 7] + str((s >> 3) + 1)


def sq_from(name):
    if len(name) != 2 or name[0] not in FILES or name[1] not in "12345678":
        raise ValueError("bad square")
    return (int(name[1]) - 1) * 8 + FILES.index(name[0])


def _build_tables():
    knight, king, rays = [], [], []
    kd = [(1, 2), (2, 1), (2, -1), (1, -2), (-1, -2), (-2, -1), (-2, 1), (-1, 2)]
    gd = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]
    for s in range(64):
        f, r = s & 7, s >> 3
        knight.append([(r + dr) * 8 + f + df for df, dr in kd if 0 <= f + df < 8 and 0 <= r + dr < 8])
        king.append([(r + dr) * 8 + f + df for df, dr in gd if 0 <= f + df < 8 and 0 <= r + dr < 8])
        rr = []
        for df, dr in gd:
            ray, ff, r2 = [], f + df, r + dr
            while 0 <= ff < 8 and 0 <= r2 < 8:
                ray.append(r2 * 8 + ff)
                ff += df
                r2 += dr
            rr.append(ray)
        rays.append(rr)
    return knight, king, rays


KNIGHT, KING, RAYS = _build_tables()
ORTHO = (0, 2, 4, 6)      # indices into RAYS: E N W S
DIAG = (1, 3, 5, 7)       # NE NW SW SE


def _is_white(p):
    return p.isupper()


class Position:
    __slots__ = ("b", "turn", "castle", "ep", "half", "full")

    def __init__(self, b, turn, castle, ep, half, full):
        self.b, self.turn, self.castle, self.ep, self.half, self.full = b, turn, castle, ep, half, full

    # ------------------------------------------------------------------ FEN
    @classmethod
    def start(cls):
        return cls.from_fen(START_FEN)

    @classmethod
    def from_fen(cls, fen):
        parts = str(fen).split()
        if len(parts) != 6:
            raise ValueError("bad fen")
        rows = parts[0].split("/")
        if len(rows) != 8:
            raise ValueError("bad fen")
        b = ["."] * 64
        for i, row in enumerate(rows):
            r, f = 7 - i, 0
            for ch in row:
                if ch.isdigit():
                    f += int(ch)
                elif ch in "PNBRQKpnbrqk" and f < 8:
                    b[r * 8 + f] = ch
                    f += 1
                else:
                    raise ValueError("bad fen")
            if f != 8:
                raise ValueError("bad fen")
        if parts[1] not in ("w", "b"):
            raise ValueError("bad fen")
        castle = "" if parts[2] == "-" else parts[2]
        if any(c not in "KQkq" for c in castle):
            raise ValueError("bad fen")
        ep = -1 if parts[3] == "-" else sq_from(parts[3])
        if b.count("K") != 1 or b.count("k") != 1:
            raise ValueError("bad fen")
        return cls(b, parts[1] == "w", castle, ep, int(parts[4]), int(parts[5]))

    def fen(self):
        rows = []
        for r in range(7, -1, -1):
            row, empty = "", 0
            for f in range(8):
                p = self.b[r * 8 + f]
                if p == ".":
                    empty += 1
                else:
                    row += (str(empty) if empty else "") + p
                    empty = 0
            rows.append(row + (str(empty) if empty else ""))
        return "%s %s %s %s %d %d" % ("/".join(rows), "w" if self.turn else "b", self.castle or "-",
                                      sq_name(self.ep) if self.ep >= 0 else "-", self.half, self.full)

    # --------------------------------------------------------------- attacks
    def attacked(self, s, by_white):
        """Is square s attacked by the given side?"""
        b = self.b
        f, r = s & 7, s >> 3
        # pawns
        pr = r - 1 if by_white else r + 1
        if 0 <= pr < 8:
            pc = "P" if by_white else "p"
            if f > 0 and b[pr * 8 + f - 1] == pc:
                return True
            if f < 7 and b[pr * 8 + f + 1] == pc:
                return True
        kn = "N" if by_white else "n"
        for t in KNIGHT[s]:
            if b[t] == kn:
                return True
        kg = "K" if by_white else "k"
        for t in KING[s]:
            if b[t] == kg:
                return True
        rq = "RQ" if by_white else "rq"
        bq = "BQ" if by_white else "bq"
        for d in ORTHO:
            for t in RAYS[s][d]:
                p = b[t]
                if p != ".":
                    if p in rq:
                        return True
                    break
        for d in DIAG:
            for t in RAYS[s][d]:
                p = b[t]
                if p != ".":
                    if p in bq:
                        return True
                    break
        return False

    def king_sq(self, white):
        return self.b.index("K" if white else "k")

    def in_check(self):
        return self.attacked(self.king_sq(self.turn), not self.turn)

    # ------------------------------------------------------------ generation
    def pseudo_moves(self):
        b, white = self.b, self.turn
        out = []
        for s in range(64):
            p = b[s]
            if p == "." or _is_white(p) != white:
                continue
            u = p.upper()
            f, r = s & 7, s >> 3
            if u == "P":
                step = 8 if white else -8
                last = 7 if white else 0
                start = 1 if white else 6
                t = s + step
                if 0 <= t < 64 and b[t] == ".":
                    if (t >> 3) == last:
                        out += [(s, t, c) for c in "qrbn"]
                    else:
                        out.append((s, t, ""))
                        if r == start and b[t + step] == ".":
                            out.append((s, t + step, ""))
                for df in (-1, 1):
                    if not 0 <= f + df < 8:
                        continue
                    t = s + step + df
                    if not 0 <= t < 64:
                        continue
                    q = b[t]
                    if q != "." and _is_white(q) != white:
                        if (t >> 3) == last:
                            out += [(s, t, c) for c in "qrbn"]
                        else:
                            out.append((s, t, ""))
                    elif t == self.ep and q == ".":
                        out.append((s, t, ""))
            elif u == "N":
                for t in KNIGHT[s]:
                    q = b[t]
                    if q == "." or _is_white(q) != white:
                        out.append((s, t, ""))
            elif u == "K":
                for t in KING[s]:
                    q = b[t]
                    if q == "." or _is_white(q) != white:
                        out.append((s, t, ""))
                # castling (squares between must be empty; check/pass-through tested here, landing square by legality filter)
                home = 4 if white else 60
                if s == home and not self.attacked(s, not white):
                    ks, qs = ("K", "Q") if white else ("k", "q")
                    rook = "R" if white else "r"
                    if ks in self.castle and b[home + 3] == rook and b[home + 1] == "." and b[home + 2] == "." \
                            and not self.attacked(home + 1, not white) and not self.attacked(home + 2, not white):
                        out.append((s, home + 2, ""))
                    if qs in self.castle and b[home - 4] == rook and b[home - 1] == "." and b[home - 2] == "." \
                            and b[home - 3] == "." and not self.attacked(home - 1, not white) \
                            and not self.attacked(home - 2, not white):
                        out.append((s, home - 2, ""))
            else:
                dirs = ORTHO if u == "R" else DIAG if u == "B" else ORTHO + DIAG
                for d in dirs:
                    for t in RAYS[s][d]:
                        q = b[t]
                        if q == ".":
                            out.append((s, t, ""))
                        else:
                            if _is_white(q) != white:
                                out.append((s, t, ""))
                            break
        return out

    def legal_moves(self):
        res = []
        white = self.turn
        for m in self.pseudo_moves():
            n = self._apply(m)
            if not n.attacked(n.king_sq(white), not white):
                res.append(m)
        return res

    # ------------------------------------------------------------------ make
    def _apply(self, m):
        frm, to, promo = m
        b = self.b[:]
        p = b[frm]
        cap = b[to]
        white = self.turn
        ep = -1
        castle = self.castle
        u = p.upper()
        if u == "P" and to == self.ep and cap == "." and (frm & 7) != (to & 7):
            b[to + (-8 if white else 8)] = "."              # en passant capture
            cap = "x"
        b[frm] = "."
        b[to] = (promo.upper() if white else promo.lower()) if promo else p
        if u == "P" and abs(to - frm) == 16:
            ep = (frm + to) // 2
        if u == "K":
            if to - frm == 2:
                b[frm + 1], b[frm + 3] = b[frm + 3], "."
            elif frm - to == 2:
                b[frm - 1], b[frm - 4] = b[frm - 4], "."
            castle = castle.replace("K", "").replace("Q", "") if white else castle.replace("k", "").replace("q", "")
        for sq, c in ((0, "Q"), (7, "K"), (56, "q"), (63, "k")):
            if frm == sq or to == sq:
                castle = castle.replace(c, "")
        half = 0 if (u == "P" or cap != ".") else self.half + 1
        return Position(b, not white, castle, ep, half, self.full + (0 if white else 1))

    def make(self, m):
        return self._apply(m)

    def parse_uci(self, s):
        """'e2e4' / 'e7e8q' -> a legal move tuple, or None."""
        if not isinstance(s, str) or len(s) not in (4, 5):
            return None
        try:
            m = (sq_from(s[:2]), sq_from(s[2:4]), s[4:].lower())
        except ValueError:
            return None
        if m[2] and m[2] not in ("q", "r", "b", "n"):
            return None
        return m if m in self.legal_moves() else None

    @staticmethod
    def uci(m):
        return sq_name(m[0]) + sq_name(m[1]) + m[2]

    # -------------------------------------------------------------------- SAN
    def san(self, m, legal=None):
        frm, to, promo = m
        b = self.b
        p = b[frm]
        u = p.upper()
        if u == "K" and abs(to - frm) == 2:
            s = "O-O" if to > frm else "O-O-O"
        else:
            capture = b[to] != "." or (u == "P" and to == self.ep and (frm & 7) != (to & 7))
            if u == "P":
                s = (FILES[frm & 7] + "x" if capture else "") + sq_name(to)
                if promo:
                    s += "=" + promo.upper()
            else:
                s = u
                legal = legal if legal is not None else self.legal_moves()
                others = [x for x in legal if x[1] == to and x[0] != frm and b[x[0]] == p]
                if others:
                    if all((x[0] & 7) != (frm & 7) for x in others):
                        s += FILES[frm & 7]
                    elif all((x[0] >> 3) != (frm >> 3) for x in others):
                        s += str((frm >> 3) + 1)
                    else:
                        s += sq_name(frm)
                s += ("x" if capture else "") + sq_name(to)
        n = self._apply(m)
        if n.in_check():
            s += "#" if not n.legal_moves() else "+"
        return s

    # ------------------------------------------------------------ draw helpers
    def key(self):
        """Position identity for repetition: pieces, side to move, castling rights, and an en-passant square only
        when a pawn could really capture there."""
        ep = -1
        if self.ep >= 0:
            pc = "P" if self.turn else "p"
            f, r = self.ep & 7, self.ep >> 3
            pr = r - 1 if self.turn else r + 1
            for df in (-1, 1):
                if 0 <= f + df < 8 and 0 <= pr < 8 and self.b[pr * 8 + f + df] == pc:
                    ep = self.ep
        return "".join(self.b) + ("w" if self.turn else "b") + "".join(sorted(self.castle)) + str(ep)

    def insufficient_material(self):
        minors, bishops_sq = [], []
        for s, p in enumerate(self.b):
            if p in ".Kk":
                continue
            if p in "PpRrQq":
                return False
            minors.append(p)
            if p in "Bb":
                bishops_sq.append(((s & 7) + (s >> 3)) & 1)
        if len(minors) <= 1:
            return True                                    # K vs K, K+minor vs K
        if all(p in "Bb" for p in minors) and len(set(bishops_sq)) == 1:
            return True                                    # only bishops, all on the same colour
        return False


def outcome(pos, keys):
    """None while the game goes on, else (result, reason). `keys` = pos.key() of every position so far (incl. pos)."""
    moves = pos.legal_moves()
    if not moves:
        if pos.in_check():
            return ("0-1" if pos.turn else "1-0", "checkmate")
        return ("1/2-1/2", "stalemate")
    if pos.insufficient_material():
        return ("1/2-1/2", "insufficient")
    if pos.half >= 100:
        return ("1/2-1/2", "fifty")
    if keys.count(pos.key()) >= 3:
        return ("1/2-1/2", "repetition")
    return None


def perft(pos, depth):
    if depth == 0:
        return 1
    ms = pos.legal_moves()
    if depth == 1:
        return len(ms)
    return sum(perft(pos.make(m), depth - 1) for m in ms)
