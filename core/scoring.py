<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>DelayDoge V14 Fast</title>
<script src="[https://telegram.org/js/telegram-web-app.js](https://telegram.org/js/telegram-web-app.js)"></script>

<style>
*{margin:0;padding:0;box-sizing:border-box;font-family:Arial,Helvetica,sans-serif}
body{min-height:100vh;background:linear-gradient(180deg,#050814,#101b33,#070b18);color:white;display:flex;justify-content:center;padding:14px;overflow-x:hidden}
.app{width:100%;max-width:430px;padding-bottom:95px}
.header{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px}
.brand{font-weight:900;color:#f7c843;font-size:20px}
.rank{background:#203869;padding:8px 13px;border-radius:999px;font-size:13px;font-weight:900}
.card,.section{background:#0f1b33;border:1px solid #2b4376;border-radius:26px}
.card{padding:16px;text-align:center;margin-bottom:14px}
.label{color:#9fb4ef;font-size:13px}
.coins{font-size:42px;font-weight:900;color:#f7c843;margin:5px 0}
.sub{font-size:13px;color:#cbd8ff}
.game-card{background:#0f1b33;border:1px solid #2b4376;border-radius:30px;padding:20px;text-align:center;position:relative;overflow:hidden;box-shadow:0 0 35px rgba(0,0,0,.45)}
.game-card.rare-flash{animation:rareFlash .45s ease}
@keyframes rareFlash{0%{box-shadow:0 0 35px rgba(0,0,0,.45)}50%{box-shadow:0 0 70px rgba(247,200,67,.7)}100%{box-shadow:0 0 35px rgba(0,0,0,.45)}}

.mascot{
width:215px;height:215px;border-radius:50%;margin:8px auto 18px;
background:radial-gradient(circle,#f7c843,#d88922);
display:flex;align-items:center;justify-content:center;
border:6px solid #203869;box-shadow:0 0 35px rgba(247,200,67,.28);
user-select:none;cursor:pointer;touch-action:manipulation;overflow:hidden;position:relative;
transition:.15s;animation:idleFloat 2.4s ease-in-out infinite;
}
.mascot:active{transform:scale(.94);box-shadow:0 0 48px rgba(247,200,67,.6)}
.mascot.tap-pulse{animation:tapPulse .22s ease}
@keyframes tapPulse{0%{transform:scale(1)}50%{transform:scale(.93)}100%{transform:scale(1)}}
#mainDoge{width:96%;height:96%;object-fit:contain;border-radius:50%;pointer-events:none;filter:drop-shadow(0 0 10px rgba(0,0,0,.35))}
@keyframes idleFloat{0%,100%{transform:translateY(0)}50%{transform:translateY(-5px)}}

.tap-text{font-size:25px;font-weight:900;color:#f7c843;margin-bottom:8px}
.combo{font-size:16px;font-weight:900;color:#35d07f;margin-bottom:10px}
.combo.fire{color:#f7c843;text-shadow:0 0 14px rgba(247,200,67,.8);animation:firePulse .6s ease infinite alternate}
@keyframes firePulse{from{transform:scale(1)}to{transform:scale(1.05)}}
.status{min-height:58px;background:#081125;border:1px solid #2b4376;border-radius:18px;padding:13px;display:flex;align-items:center;justify-content:center;font-size:15px;line-height:1.35;color:#dbe5ff;margin-bottom:14px}
.energy-top{display:flex;justify-content:space-between;font-size:13px;color:#9fb4ef;margin-bottom:6px}
.energy-bar{width:100%;height:14px;background:#081125;border-radius:999px;overflow:hidden;border:1px solid #2b4376}
.energy-fill{height:100%;width:100%;background:linear-gradient(90deg,#35d07f,#f7c843);transition:.1s}
.stats{display:grid;grid-template-columns:1fr 1fr 1fr;gap:9px;margin-top:13px}
.box{background:#081125;border:1px solid #2b4376;border-radius:17px;padding:12px 8px}
.small{font-size:11px;color:#9fb4ef;margin-bottom:5px}
.num{font-size:18px;font-weight:900}
.section{margin-top:14px;padding:16px}
.section h3{font-size:18px;color:#f7c843;margin-bottom:10px}
.feed{font-size:14px;color:#dbe5ff;line-height:1.8}
.task{display:flex;justify-content:space-between;align-items:center;background:#081125;border:1px solid #2b4376;padding:12px;border-radius:15px;margin-bottom:9px}
.btn{border:none;padding:10px 12px;border-radius:12px;background:#f7c843;color:#07101f;font-weight:900;cursor:pointer;touch-action:manipulation}
.btn.dark{background:#203869;color:#fff}
.btn.full{width:100%;padding:14px;margin-top:8px;font-size:16px}
.nav{position:fixed;bottom:12px;left:50%;transform:translateX(-50%);width:calc(100% - 28px);max-width:430px;display:grid;grid-template-columns:repeat(4,1fr);gap:8px;background:#0b1326;border:1px solid #2b4376;padding:8px;border-radius:22px;z-index:60}
.nav button{border:none;background:#111f3f;color:white;border-radius:15px;padding:10px 4px;font-size:12px;font-weight:900}
.nav button.active{background:#f7c843;color:#07101f}
.hidden{display:none}
.popup{position:fixed;top:18px;left:50%;transform:translateX(-50%);background:#f7c843;color:#07101f;padding:12px 18px;border-radius:999px;font-weight:900;opacity:0;pointer-events:none;transition:.25s;z-index:99}
.popup.show{opacity:1;top:28px}
.float{position:absolute;color:#f7c843;font-weight:900;font-size:22px;pointer-events:none;animation:floatUp .8s ease-out forwards;text-shadow:0 0 12px rgba(247,200,67,.6)}
@keyframes floatUp{from{opacity:1;transform:translateY(0) scale(1)}to{opacity:0;transform:translateY(-70px) scale(1.35)}}
.coin-particle{position:absolute;width:9px;height:9px;border-radius:50%;background:#f7c843;box-shadow:0 0 12px rgba(247,200,67,.75);pointer-events:none;animation:coinBurst .7s ease-out forwards}
@keyframes coinBurst{from{opacity:1;transform:translate(0,0) scale(1)}to{opacity:0;transform:translate(var(--dx),var(--dy)) scale(.3)}}

.overlay{position:fixed;inset:0;background:rgba(0,0,0,.78);display:none;align-items:center;justify-content:center;z-index:120;padding:20px}
.modal{
width:100%;max-width:370px;background:linear-gradient(180deg,#102044,#081125);
border:2px solid #f7c843;border-radius:30px;padding:22px 18px;text-align:center;
box-shadow:0 0 55px rgba(247,200,67,.38);animation:eventPop .22s ease-out;
}
@keyframes eventPop{from{transform:scale(.9);opacity:.3}to{transform:scale(1);opacity:1}}
.event-image{width:210px;height:210px;object-fit:contain;margin:0 auto 12px;display:none;filter:drop-shadow(0 0 18px rgba(247,200,67,.45))}
.modal-icon{font-size:78px;margin-bottom:12px}
.modal-title{font-size:28px;color:#f7c843;font-weight:900;margin-bottom:10px}
.modal-text{font-size:16px;color:#fff;margin-bottom:18px;line-height:1.5}
.event-effect{font-size:14px;color:#35d07f;font-weight:900;margin-bottom:12px}

.telegram-only{min-height:100vh;width:100%;max-width:430px;display:none;align-items:center;justify-content:center;text-align:center;padding:24px}
.telegram-only-card{background:#0f1b33;border:1px solid #2b4376;border-radius:28px;padding:24px}
.telegram-only-card h2{color:#f7c843;margin-bottom:10px}
.telegram-only-card p{color:#cbd8ff;line-height:1.6;font-size:15px}
.invite-link{font-size:12px;color:#cbd8ff;word-break:break-all;background:#081125;border:1px solid #2b4376;border-radius:14px;padding:10px;margin-top:8px}
.flash{animation:flash .35s ease}
@keyframes flash{0%{transform:scale(1)}50%{transform:scale(1.04)}100%{transform:scale(1)}}
.shake{animation:shake .25s}
@keyframes shake{0%,100%{transform:translateX(0)}25%{transform:translateX(-5px)}75%{transform:translateX(5px)}}
.gang-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.gang-card{background:#081125;border:1px solid #2b4376;border-radius:18px;padding:12px;text-align:center;min-height:205px;position:relative;overflow:hidden}
.gang-icon{font-size:42px;margin-bottom:7px}
.gang-img{width:100%;height:108px;object-fit:contain;background:#ffffff;border-radius:14px;margin-bottom:8px;border:1px solid #2b4376}
.gang-name{font-weight:900;color:#f7c843;font-size:14px;margin-bottom:4px}
.gang-role{font-size:11px;color:#9fb4ef;margin-bottom:6px}
.gang-desc{font-size:11px;color:#dbe5ff;line-height:1.35}
.locked{opacity:.45;filter:grayscale(1)}
.badge{position:absolute;top:8px;right:8px;background:#203869;color:white;border-radius:999px;padding:4px 7px;font-size:10px;font-weight:900;z-index:3}
.unlocked{background:#35d07f;color:#07101f}
</style>
</head>

<body>

<div class="telegram-only" id="telegramOnly">
  <div class="telegram-only-card">
    <h2>🐶 Open from Telegram</h2>
    <p>افتح اللعبة من زر تيليجرام الرسمي داخل البوت عشان تنحفظ نقاطك بنفس الحساب.</p>
  </div>
</div>

<div class="popup" id="popup">+1</div>

<div class="overlay" id="modalOverlay">
  <div class="modal">
    <img id="eventImage" class="event-image" src="" alt="">
    <div class="modal-icon" id="modalIcon">🎁</div>
    <div class="modal-title" id="modalTitle">Loot Box</div>
    <div class="modal-text" id="modalText">Reward</div>
    <div class="event-effect" id="eventEffect"></div>
    <button class="btn full" onclick="closeModal()">CONTINUE</button>
  </div>
</div>

<div class="app" id="app">
  <div class="header">
    <div class="brand">🐶 DelayDoge</div>
    <div class="rank" id="rank">Rookie</div>
  </div>

  <div id="homePage">
    <div class="card">
      <div class="label">Your Delay Points</div>
      <div class="coins" id="coins">0</div>
      <div class="sub">Tap fast. Build combo. Unlock the Delay Gang.</div>
    </div>

    <div class="game-card" id="gameCard">
      <div class="mascot" onclick="tapDeliver(event)" id="mascot">
        <img src="assets/characters/delaydoge-official.png" id="mainDoge" alt="DelayDoge">
      </div>

      <div class="tap-text">TAP DELAYDOGE</div>
      <div class="combo" id="comboText">Combo: x1</div>
      <div class="status" id="status">DelayDoge is waiting for the next package...</div>

      <div class="energy-top"><span>Energy</span><span id="energyText">100/100</span></div>
      <div class="energy-bar"><div class="energy-fill" id="energyFill"></div></div>

      <div class="stats">
        <div class="box"><div class="small">XP</div><div class="num" id="xp">0</div></div>
        <div class="box"><div class="small">Taps</div><div class="num" id="taps">0</div></div>
        <div class="box"><div class="small">Level</div><div class="num" id="level">1</div></div>
      </div>
    </div>

    <div class="section">
      <h3>🔥 Live Feed</h3>
      <div class="feed" id="feed">Loading player data...</div>
    </div>
  </div>

  <div id="tasksPage" class="hidden">
    <div class="section">
      <h3>✅ Daily Missions</h3>
      <div class="task"><span>Tap 50 times</span><button class="btn" onclick="comingSoon()">Claim</button></div>
      <div class="task"><span>Daily Streak Reward</span><button class="btn" onclick="comingSoon()">Claim</button></div>
      <div class="task"><span>Open Mystery Box</span><button class="btn" onclick="comingSoon()">Open</button></div>
      <button class="btn full dark" onclick="shareTelegram()">📨 Share DelayDoge</button>
    </div>
  </div>

  <div id="invitePage" class="hidden">
    <div class="section">
      <h3>🔗 Invite & Earn</h3>
      <p style="font-size:14px;color:#cbd8ff;line-height:1.6">Invite a friend. Rewards will be activated soon.</p>
      <div class="invite-link" id="inviteLink"></div>
      <button class="btn full" onclick="copyInvite()">Copy Invite Link</button>
      <button class="btn full dark" onclick="shareTelegram()">Share to Telegram</button>
    </div>
  </div>

  <div id="gangPage" class="hidden">
    <div class="section">
      <h3>🐾 Delay Gang</h3>
      <div class="gang-grid" id="gangGrid"></div>
    </div>
    <div class="section">
      <h3>🎭 Skins</h3>
      <div class="gang-grid" id="skinsGrid"></div>
    </div>
  </div>
</div>

<div class="nav" id="nav">
  <button id="navHome" class="active" onclick="showPage('home')">Home</button>
  <button id="navTasks" onclick="showPage('tasks')">Tasks</button>
  <button id="navInvite" onclick="showPage('invite')">Invite</button>
  <button id="navGang" onclick="showPage('gang')">Gang</button>
</div>

<script>
const API_BASE = "[https://delaydoge-api.onrender.com](https://delaydoge-api.onrender.com)";

let tg = null;
let tgUser = null;
let referralCode = null;
let userId = null;
let tgInitData = "";

let coins = 0;
let xp = 0;
let taps = 0;
let energy = 100;
let level = 1;
let combo = 1;
let lastTapTime = 0;

let tapBuffer = 0;
let syncInProgress = false;

const statuses = [
  "DelayDoge moved the package 2 meters. Bullish 📦",
  "Driver took lunch and vanished 🍔",
  "Out for delivery since yesterday 😂",
  "Package delayed emotionally 😭",
  "Tracking says: still suffering",
  "Warehouse forgot it exists 💀",
  "Delivered to someone named Not You",
  "Customs opened it for emotional support."
];

const gang = [
  {icon:"🐶",img:"assets/characters/delaydoge-official.png",name:"DelayDoge",role:"The Main Legend",desc:"Cold, late, and proud.",unlock:0},
  {icon:"⚡",img:"assets/characters/express-cat.png",name:"Express Cat",role:"The Rival",desc:"Fast and furious.",unlock:300},
  {icon:"🛃",img:"assets/characters/customs-boss.png",name:"Customs Boss",role:"The Gatekeeper",desc:"Stops packages.",unlock:1800}
];

function showTelegramOnly() {
  document.getElementById("app").style.display = "none";
  document.getElementById("nav").style.display = "none";
  document.getElementById("telegramOnly").style.display = "flex";
}

function bootTelegram() {
  tg = window.Telegram?.WebApp || null;
  if (!tg) {
    setTimeout(() => {
      tg = window.Telegram?.WebApp || null;
      if (!tg) return showTelegramOnly();
      continueBoot();
    }, 1000);
    return;
  }
  continueBoot();
}

function continueBoot() {
  try {
    tg.ready();
    tg.expand();
  } catch (e) {}

  setTimeout(() => {
    tgInitData = tg?.initData || "";
    tgUser = tg?.initDataUnsafe?.user || null;
    
    if (!tgUser || !tgUser.id) return showTelegramOnly();
    
    userId = "tg_" + tgUser.id;
    refresh();
    loginUser();
  }, 500);
}

async function api(path, options = {}) {
  const res = await fetch(API_BASE + path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok && !data.error) data.error = "Request failed";
  return data;
}

async function loginUser() {
  try {
    const result = await api("/auth", {
      method: "POST",
      body: JSON.stringify({ initData: tgInitData })
    });

    if (result.error || !result.player) {
      setFeed("Login failed.");
      return;
    }

    // هنا فقط نقوم بجلب البيانات لأول مرة من السيرفر
    applyPlayer(result.player);
    setFeed("Player loaded safely ✅");
  } catch (e) {
    setFeed("Server sync issue.");
  }
}

function applyPlayer(p) {
  if (!p) return;
  coins = Number(p.points ?? 0);
  xp = Number(p.xp ?? 0);
  taps = Number(p.taps ?? 0);
  energy = Number(p.energy ?? 100);
  level = Number(p.level ?? Math.floor(Math.sqrt(xp / 100)) + 1);
  refresh();
}

function refresh() {
  document.getElementById("coins").innerText = coins;
  document.getElementById("xp").innerText = xp;
  document.getElementById("taps").innerText = taps;
  document.getElementById("level").innerText = level;
  document.getElementById("energyText").innerText = energy + "/100";
  document.getElementById("energyFill").style.width = Math.max(0, Math.min(100, energy)) + "%";
}

// ==========================================
// التحديث الفوري المباشر - (السبب في زيادة الرقم فوراً)
// ==========================================
function tapDeliver(e) {
  if (!userId || !tgUser) return;
  if (energy <= 0) return;

  const now = Date.now();
  combo = now - lastTapTime < 650 ? Math.min(combo + 1, 5) : 1;
  lastTapTime = now;

  // تحديث الأرقام داخلياً فوراً وبدون انتظار
  coins += combo;
  xp += (combo * 2);
  energy -= 1;
  taps += 1;
  level = Math.floor(Math.sqrt(xp / 100)) + 1;

  // إجبار واجهة المستخدم على التغيير في نفس اللحظة
  document.getElementById("coins").innerText = coins;
  document.getElementById("xp").innerText = xp;
  document.getElementById("taps").innerText = taps;
  document.getElementById("level").innerText = level;
  document.getElementById("energyText").innerText = energy + "/100";
  document.getElementById("energyFill").style.width = Math.max(0, Math.min(100, energy)) + "%";

  // مؤثرات بصرية
  const comboText = document.getElementById("comboText");
  comboText.innerText = combo >= 4 ? "🔥 FIRE COMBO x" + combo : "Combo: x" + combo;
  comboText.classList.toggle("fire", combo >= 4);

  createFloat(e, "+" + combo);
  createCoinBurst(e);
  pulseMascot();

  if (navigator.vibrate) navigator.vibrate(22);

  // تسجيل الضغطة لإرسالها في الخلفية
  tapBuffer++;
  if (tapBuffer >= 10) {
    syncTapBuffer();
  }
}

// ==========================================
// إرسال البيانات للسيرفر بصمت تام
// ==========================================
async function syncTapBuffer() {
  if (syncInProgress || tapBuffer <= 0) return;

  syncInProgress = true;
  const tapsToSend = Math.min(tapBuffer, 30);
  tapBuffer -= tapsToSend;

  try {
    const r = await api("/tap", {
      method: "POST",
      body: JSON.stringify({ initData: tgInitData, taps: tapsToSend })
    });

    if (!r.error) {
      // لا نقم بتعديل النقاط هنا أبداً! المتصفح هو من يحسب النقاط أثناء اللعب
      // هذا يمنع أي تعليق أو تراجع في الأرقام
      document.getElementById("status").innerText = "Synced safely ✅";
    } else {
      tapBuffer += tapsToSend; // إعادة المحاولة إذا فشل
    }
  } catch (e) {
    tapBuffer += tapsToSend;
  }

  syncInProgress = false;
  if (tapBuffer > 0) setTimeout(syncTapBuffer, 250);
}

// المؤثرات البصرية
function pulseMascot() {
  const m = document.getElementById("mascot");
  m.classList.remove("tap-pulse");
  void m.offsetWidth;
  m.classList.add("tap-pulse");
  setTimeout(() => m.classList.remove("tap-pulse"), 230);
}

function createCoinBurst(e) {
  const card = document.getElementById("gameCard");
  const rect = card.getBoundingClientRect();
  const baseX = e.clientX ? e.clientX - rect.left : rect.width / 2;
  const baseY = e.clientY ? e.clientY - rect.top : 160;

  for (let i = 0; i < 6; i++) {
    const p = document.createElement("div");
    p.className = "coin-particle";
    const angle = Math.random() * Math.PI * 2;
    const dist = 35 + Math.random() * 38;
    p.style.left = baseX + "px";
    p.style.top = baseY + "px";
    p.style.setProperty("--dx", Math.cos(angle) * dist + "px");
    p.style.setProperty("--dy", Math.sin(angle) * dist - 45 + "px");
    card.appendChild(p);
    setTimeout(() => p.remove(), 720);
  }
}

function createFloat(e, text) {
  const card = document.getElementById("gameCard");
  const f = document.createElement("div");
  f.className = "float";
  f.innerText = text;
  const rect = card.getBoundingClientRect();
  const x = e.clientX ? e.clientX - rect.left : rect.width / 2;
  const y = e.clientY ? e.clientY - rect.top : 160;
  f.style.left = x + "px";
  f.style.top = y + "px";
  card.appendChild(f);
  setTimeout(() => f.remove(), 800);
}

function showPage(p) {
  ["home", "tasks", "invite", "gang"].forEach(x => {
    document.getElementById(x + "Page").classList.add("hidden");
    document.getElementById("nav" + cap(x)).classList.remove("active");
  });
  document.getElementById(p + "Page").classList.remove("hidden");
  document.getElementById("nav" + cap(p)).classList.add("active");
}

function cap(s) { return s.charAt(0).toUpperCase() + s.slice(1); }
function setFeed(html) { document.getElementById("feed").innerHTML = html; }
function comingSoon() { alert("Coming soon"); }

setInterval(() => {
  if (tapBuffer > 0) syncTapBuffer();
}, 2000);

bootTelegram();
</script>
</body>
</html>
