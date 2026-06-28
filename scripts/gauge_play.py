"""Cheap Codex-recovery gauge: ONE play turn on an existing shelf world, timed. Tests the exact
failure mode that hung (play turns / open_scene), without a 34-min build."""
import time, logging
logging.basicConfig(level=logging.ERROR)
from construct.provider import CodexProvider
from construct.session import Session
t0=time.time()
try:
    s=Session.open("anchor", player_id="gauge", fresh=True, provider=CodexProvider())
    op=s.opening(); t_open=time.time()-t0
    r=s.turn("I look around and take stock of who is here."); t_turn=time.time()-t0
    s.close()
    print(f"PLAY OK — opening {t_open:.0f}s, +turn {t_turn:.0f}s total; prose_len={len(r.prose or '')}")
except Exception as e:
    print(f"PLAY FAILED in {time.time()-t0:.0f}s — {e}")
