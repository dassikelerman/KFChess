# KungFu Chess — תכנון ארכיטקטורה: Bus + Client/Server

מסמך תכנון לפני מימוש. מבוסס על: קוד הפרויקט הקיים, מצגת CTD 26, וקובץ ה-Word "מה צריך להוסיף". מטרתו: לרכז את כל ההחלטות שהתקבלו כדי שיהיה קל להעביר אותו כרפרנס לכל שיחת מימוש (כולל ל-Claude Code).

---

## פיצ'ר 1: Pub/Sub Bus — **הושלם**

- `events/dispatcher.py` (`EventDispatcher`) היה כבר קיים ומתאים במדויק לדרישה — הבדל ה-Pub/Sub מ-Observer: אין קשר ישיר בין מפרסם למאזין, התיווך הוא לפי טיפוס אירוע.
- `ScoreTracker` ו-`ActionHistory` כבר נרשמו ל-dispatcher לפני תחילת העבודה.
- נוסף `SoundSystem` (`events/sound_system.py`) לפי אותה תבנית בדיוק:
  - נרשם ל-5 אירועים: `MoveCompletedEvent`, `CaptureEvent`, `PromotionEvent`, `GameOverEvent`, ול-**אירוע חדש** `IllegalActionEvent` (`piece_id: Optional`, `destination`, `at_ms` — **בלי שדה reason**, בכוונה — ראו החלטה #5 למטה).
  - ה-callbacks רק ממלאים תור (`drain_pending()`), לא נוגעים ב-audio API בתוך ה-callback — כדי להישאר thread-safe כשמקור האירועים יהפוך לרשת.
  - השמעה בפועל קורית רק בלולאת ה-view הראשית, פעם בפריים.
  - `winsound` (Windows-only) נבחר במקום `pygame` — תקף כי הצד ש**מנגן** סאונד הוא תמיד ה-client (Windows), לא ה-server. **נקודה לזכור:** אם השרת ירוץ אי-פעם על Linux, זה לא רלוונטי אליו כי הוא לא מנגן סאונד בכלל.
  - `IllegalActionEvent` מתפרסם מ-`GameEngine.request_move/request_jump` בכל נתיב דחייה קיים (JUMP_IN_PROGRESS, RESTING, EMPTY_SOURCE, ולידציה לא תקינה).
- אנימציות פתיחה/סיום משחק — **לא בעדיפות כרגע**, הוחלט לדלג.

---

## פיצ'ר 2: מעבר ל-Client/Server מקומי + WebSocket — **הושלם**

### עקרון-על
**Server authoritative, thin client.** השרת מחזיק את המופע היחיד של `GameEngine` לכל משחק; הקליינט שולח כוונות בלבד ומצייר את מה שהשרת אומר. נבחר על פני client-side prediction כי המשחק לוקאלי (לא רגיש ל-latency ברמה שמצדיקה את המורכבות), וכי `EventDispatcher` כבר תוכנן לזה מראש (docstring מזכיר `NetworkPublisher` כצרכן עתידי).

### מבנה תיקיות (מצב בפועל אחרי סיום)
```
kf-chess/
├── app/ board_io/ engine/ model/ realtime/ rules/   ← ללא שינוי
├── events/
│   ├── dispatcher.py, game_events.py                ← ללא שינוי
│   ├── score_tracker.py, action_history.py,
│   │   sound_system.py                              ← ללא שינוי
│   └── serialization.py                             ← חדש (+ snapshot_to_payload, ראו למטה)
├── input/
│   ├── controller.py                                ← שינוי קטן: מקבל ActionSink + read-model נפרדים
│   └── controller_builder.py                        ← build_controller, משותף בין view/text/client (ראו למטה)
├── view/                         ← ללא שינוי התנהגותי; game_ui_snapshot.py (build_ui_snapshot) הפך למשותף עם client
├── text/                         ← ללא שינוי
├── server/
│   ├── session.py                ← חדש — אוכף בעלות צבע
│   ├── network_publisher.py      ← חדש — רק broadcast/unicast של אירועי דומיין (לא בונה snapshot)
│   ├── game_loop.py              ← חדש — לולאת הטיק, חולצה מ-ws_server.py
│   └── ws_server.py              ← חדש (entry point)
├── client/
│   ├── snapshot_view.py          ← חדש
│   ├── ws_client.py              ← חדש
│   └── run.py                    ← חדש (entry point)
└── tests/                        ← + test_network_publisher, test_serialization, test_snapshot_view, test_session, test_game_loop, test_controller_builder, test_game_ui_snapshot וכו'
```
`view/run.py` הקיים **לא נמחק** — נשאר כמסלול פיתוח/דיבוג מהיר בלי רשת, ו-`client/run.py` הוא תוסף עליו, לא תחליף.

### מודולים חדשים ואחריות

| מודול | אחריות |
|---|---|
| `events/serialization.py` | `to_dict`/`from_dict` ל-`GameSnapshot`/`PieceSnapshot` ולכל אירוע ב-`game_events.py`, עם תג `type` לשחזור. הודעות קליינט→שרת: `MoveIntent{from,to}`, `JumpIntent{position}`. גם `snapshot_to_payload(snapshot, clock_ms)` — helper טהור (בלי שליחה/mutation) שהופך `GameSnapshot`+שעון לdict מוכן לרשת; הוצא מתוך `NetworkPublisher` כדי שלא יערבב בין "מאזין לדיספצ'ר" לבין "בניית snapshot". |
| `input/controller_builder.py` | `build_controller(action_sink, state_reader, board_width, board_height, *, cell_size, x_offset=0, y_offset=0)` — לא מניח `GameEngine`, רק את הפעולות המשותפות. מסלולים מקומיים (`view/run.py`, `text/run.py`) מעבירים את אותו `GameEngine` גם כ-action_sink וגם כ-state_reader; הקליינט (`client/run.py`) מעביר `ws_client` כ-action_sink ו-`snapshot_view` כ-state_reader. |
| `view/game_ui_snapshot.py` | `build_ui_snapshot(state_source, controller, score_tracker, action_history)` — גם כאן לא מניח `GameEngine`, רק `snapshot()`/`.clock`; `client/run.py` משתמש באותה פונקציה בדיוק במקום לבנות `GameUiSnapshot` ידנית. |
| `server/session.py` | משחק/חדר בודד. עוטף `GameComponents`. מחזיק מיפוי connection→role (White/Black/Spectator). `handle_client_message(connection, msg)`, `tick(dt_ms)`. **כאן, ולא ב-GameEngine, נבדקת בעלות הצבע** — דחייה (גם מבעלות וגם מ-`ActionResult` של GameEngine) משודרת unicast בלבד ל-connection ששלח, אף פעם לא broadcast. |
| `server/network_publisher.py` | subscriber ל-dispatcher של ה-Session (כמו `ScoreTracker`). משדר אירועי דומיין יוצאים (broadcast) ומנתב `IllegalActionEvent` ל-unicast בלבד. **לא בונה snapshot** — זה עבר ל-`events/serialization.snapshot_to_payload` + `ws_server.py`, כדי ש-`NetworkPublisher` יישאר אחראי רק על העברת אירועים, לא על בניית מצב. |
| `server/game_loop.py` | `run_game_loop(session, broadcast_snapshot, tick_ms)` — לולאת הטיק עצמה, חולצה מתוך `ws_server.py`: ישן, מודד זמן אמיתי, קורא ל-`session.tick(dt_ms)`, ואז ל-`broadcast_snapshot()` שמוזרק מבחוץ. בלי שום ידיעה על websockets/JSON/connections. |
| `server/ws_server.py` | entry point. בונה `Session`+`NetworkPublisher`, מנהל connections, broadcast/unicast בפועל, מטפל בחיבור/ניתוק והודעות נכנסות, ומפעיל את `server/game_loop.run_game_loop`. |
| `client/snapshot_view.py` | read-model מקומי: `piece_at`, `is_busy` כ-lookup טהור מעל ה-`GameSnapshot` האחרון שהתקבל. |
| `client/ws_client.py` | thread נפרד עם asyncio loop משלו; שתי `queue.Queue()` (נכנס/יוצא) לתקשורת עם ה-thread הראשי. |
| `client/run.py` | לולאה ראשית (מבנה זהה ל-`view/run.py` הקיים, ומשתמשת באותם `build_controller`/`build_ui_snapshot`): שואבת queue נכנס → מעדכנת `SnapshotView` + מפרסמת מחדש לדיספצ'ר מקומי → מציירת → קולטת קליק → דוחפת intent ל-queue יוצא. |

### החלטות עיצוב (עם הנימוק)

1. **Server authoritative, לא client-side prediction.** מנוע יחיד-אמת בצד שרת; הקליינט "טיפש".
2. **`websockets` (asyncio)**, לא `Flask-SocketIO`/`socket` גולמי — קליל ומתאים להיקף הפרויקט.
3. **טיק המנוע (`engine.wait`) רץ בלולאה עצמאית בצד השרת**, מנותק לגמרי מקצב הציור של כל קליינט.
4. **`ActionSink` הוא write-only** (`request_move`/`request_jump`). קריאות state (`piece_at`, `is_busy`) **לא** עוברות ברשת בכלל — נקראות מקומית מול `SnapshotView`, כי `Controller` קורא להן כל פריים (`refresh_selection`), לא רק בלחיצה. הניחוש המקומי יכול להיות "טעות" (מידע לא עדכני) — זה תקין, כי השרת נשאר סמכות בפועל ופשוט דוחה בקשות שגויות.
   - `GameSnapshot`/`PieceSnapshot` הקיימים כבר מכילים כמעט את כל השדות הדרושים (`id`, `row/col`, `is_jumping`, `rest_fraction_remaining`).
   - **לבדוק במימוש בפועל:** `is_busy` היום נגזר מ-`arbiter.is_jumping_on(cell)` (מפתח לפי תא) — לוודא בטסט שזה נגזר נכון מ-`PieceSnapshot.is_jumping`+`row/col`, לא רק להניח.
5. **דחיית פעולה מסיבת בעלות (למשל White מנסה להזיז כלי שחור) — מטופלת ע"י Session, לא GameEngine.**
   - Session מפרסמת בעצמה `IllegalActionEvent` על אותו dispatcher (בדיוק כמו ש-GameEngine כבר עושה) — לא נוסף שדה `reason` לאירוע, כי גם היום אף consumer לא מבחין בין סיבות דחייה שונות; להוסיף reason רק למקרה הזה יוצר א-סימטריה בלי צרכן אמיתי.
   - `network_publisher` מבחין בין broadcast (`Move/Capture/Jump/Promotion/GameOver` — עובדה משותפת) ל-**unicast** (`IllegalActionEvent` — כישלון אישי, נשלח רק ל-connection שניסה את הפעולה, לא לכל השחקנים/צופים).
6. **קליינט יחיד ששולט בשני הצבעים (למבחנים) — מומש, ואז הוסר לגמרי.**
   - מומש כפי שתוכנן: `Session(allow_single_client_both_colors=True)` + `--dev-single-client` ב-`ws_server.py`, כבוי כברירת מחדל.
   - **הוחלט להסיר את כל הפיצ'ר** — הוא הוסיף סניף קבוע לנתיב אכיפת הבעלות (security-relevant) רק בשביל נוחות בבדיקות ידניות; לא שווה את זה. `_connection_owns_color` חזרה להיות השוואת role↔color פשוטה בלבד.
   - למבחנים בלי רשת בכלל, `view/run.py` הקיים ממשיך לספק את זה (אין auth check שם) — נשאר מסלול ה-fallback התקין.
7. **שילוב OpenCV + asyncio בקליינט:** `ws_client` רץ על thread רשת נפרד, מתקשר עם ה-thread הראשי (שחייב להריץ את `cv2`) דרך שתי `queue.Queue()` — אותה תבנית producer/consumer שכבר קיימת ועובדת ב-`SoundSystem.drain_pending()`, לא פרדיגמה חדשה.

### הרצף המלא (מהתחלה ועד תגובה לקליק)
1. שרת עולה → `Session` יחיד (hardcoded בשלב זה — matchmaking/rooms אמיתיים מגיעים בפיצ'רים 5-6) → מריץ טיק לולאה.
2. קליינט A מתחבר → מוקצה White + snapshot התחלתי. קליינט B מתחבר → מוקצה Black.
3. קליק → `Controller` מחליט מול `SnapshotView` המקומי → שולח `MoveIntent` דרך `ws_client`.
4. Session מקבל → בודק בעלות צבע → קורא ל-`engine.request_move` (ללא שינוי בו) → אם נדחה (משתי הסיבות, בעלות או מנוע) → `IllegalActionEvent` → unicast → `SoundSystem` המקומי של אותו קליינט מנגן `illegal_move.wav`.
5. כל טיק: `server/game_loop.run_game_loop` ישן, מודד זמן אמיתי, קורא ל-`session.tick(dt_ms)` → `engine.wait` מקדם תנועות → אירועי דומיין אמיתיים נורים ומשודרים דרך `NetworkPublisher` → ובמקביל `ws_server.py` בונה snapshot מלא (`events/serialization.snapshot_to_payload`) ומשדר אותו לכולם → כל קליינט מעדכן `SnapshotView` ומפרסם מחדש מקומית → `SoundSystem`/`ScoreTracker`/`ActionHistory` (ללא שינוי בהם) מגיבים בדיוק כמו במצב לוקאלי היום.

### מה נשאר פתוח בכוונה (להמשך, לא עכשיו)
ניתוק שחקן + ספירה לאחור (פיצ'ר 5), matchmaking אמיתי ו-rooms (פיצ'רים 5-6) — `Session` מתוכננת כך שיהיה קל להרחיב אליהם (מיפוי sessions לפי id, role `Spectator` כבר קיים כאפשרות), אך לא ממומשים בשלב זה.

---

## פיצ'ר 3: Username דרך CMD (ללא סיסמה, ללא DB)

**מקור:** "Login with username (just for presentation)... Do it in a shell, not via GUI." + אישור מהמשתמשת: "פשוט מתחברים ומשחקים" — ללא אימות אמיתי. "ראשון=White שני=Black" **כבר קיים ועובד** (`assign_role`, מפיצ'ר 2) — אין נגיעה בזה כלל.

**החלטה מרכזית: אין DB בשלב הזה.** ה-username זמני וחי רק כל עוד ה-connection פתוח (בזיכרון, בתוך `Session`) — נעלם עם סגירת התהליך. DB (SQLite) נכנס לתמונה רק בפיצ'ר 4, כי רק שם יש שני דברים שבאמת דורשים התמדה בין הרצות: סיסמה לאימות, ו-rating שצריך להצטבר לאורך זמן. בלי אחד מהשניים, אין סיבה לפתוח DB.

**זרימה סופית שהוחלטה:**
1. `client/run.py`: `input("Username: ")` בטרמינל — **לפני** פתיחת חיבור ה-WebSocket, לפני כל חלון גרפי. ולידציה בסיסית בלבד: לא ריק (אם ריק, שואל שוב) — אין בדיקת ייחודיות, זה מגיע בפיצ'ר 4.
2. מיד עם החיבור, הקליינט שולח הודעת `Login{username}` **לפני** שהשרת שולח `role` — סדר ההודעות משתנה: היום השרת שולח `role`+snapshot מיד עם החיבור; מעכשיו הוא **מחכה** להודעת Login ראשונה, ורק אז ממשיך כרגיל.
3. `Session` שומרת מיפוי `connection -> username` (מבנה זהה למיפוי `connection -> role` הקיים), ומדפיסה לוג שרת ("White connected as Dana").
4. הקליינט מדפיס בטרמינל "מחוברת בתור {username} ({role})" **לפני** שהוא פותח את חלון ה-cv2 — משוב ברור ש"ההתחברות הצליחה" לפני מעבר לגרפיקה.
5. **לא** מוצג username על גבי המסך/פאנל הניקוד/לוג המהלכים בשלב הזה — נשאר שיפור טבעי לפיצ'ר 4, כשה-username הופך משמעותי (rating).

---

## פיצ'ר 4: Username+Password (SQLite) + Rating (ELO) — **הושלם**

**החלטות שהתקבלו לפני קוד:**

1. **זרימה אחת, לא Login/הרשמה נפרדים** — username+password דרך CMD (כמו פיצ'ר 3, רק עם עוד שדה). אם ה-username לא קיים ב-DB → נוצר חשבון חדש, rating=1200. אם קיים → מאמתים סיסמה.
2. **סיסמה שגויה → סגירת חיבור**, בלי retry על אותו handshake (עקבי עם איך שטופל login לא-תקין בפיצ'ר 3). הקליינט יכול לפתוח חיבור חדש בעצמו אם המשתמשת רוצה לנסות שוב.
3. **אחסון סיסמה:** hash+salt דרך `hashlib.pbkdf2_hmac` (stdlib, בלי תלות חדשה). **הבהרה חשובה:** הסיסמה עדיין עוברת ברשת בטקסט גלוי (אין TLS/`wss://` בפרויקט) — ה-hashing מגן רק על מה שנשמר בקובץ ה-DB, לא על מה שעובר ברשת. מגבלה ידועה וסבירה בהיקף הזה.
4. **סכימה:** טבלה אחת `users` (`username` PK, `password_hash`, `password_salt`, `rating` default 1200). קובץ `server/kf_chess_users.db`, נוצר אוטומטית (`CREATE TABLE IF NOT EXISTS`) בעליית השרת.
5. **`sqlite3` סינכרוני רגיל (stdlib), לא `aiosqlite`** — בהיקף של כמה שחקנים בו-זמנית שאילתה בודדת לא צפויה לחסום את ה-event loop היחיד בצורה מורגשת. לשקול מחדש רק אם ההיקף יגדל משמעותית.
6. **Rating מתעדכן רק בסיום משחק אמיתי** (`GameOverEvent` הקיים) — לא במהלך המשחק. נוסחת ELO סטנדרטית, K=32. `Session` (שכבר יודעת `connection -> username` ו-`connection -> role`) ממפה `winner_color` לזוג ה-usernames ומעדכנת את שניהם ב-DB יחד.
7. **תוספת מימוש:** "הקליינט יכול לפתוח חיבור חדש בעצמו" (החלטה #2 למעלה) מומש בפועל כלולאת retry אוטומטית בתוך `client/run.py` — לא צריך להריץ את התהליך מחדש: סיסמה שגויה מדפיסה "login failed" וחוזרת ישר ל-`getpass` עם `WsClient` חדש לגמרי (הישן לעולם לא נעשה בו שימוש חוזר). כדי שה-thread הרקעי של `WsClient` ידע לדווח על סגירה כזו במקום פשוט "למות" בשקט, `ws_client.py` תופס `websockets.ConnectionClosed` ודוחף פריט `("closed", reason)` לתור ה-inbound.

---

## תזכורת: מפת הדרכים המלאה
1. ✅ BUS (Pub/Sub)
2. ✅ Client/Server מקומי + WebSocket
3. ✅ Username דרך CMD (ללא סיסמה/DB)
4. ✅ Username+Password (SQLite) + Rating (ELO, מתחיל 1200)
5. כפתור PLAY — matchmaking לפי ELO±100, MessageBox אם לא נמצא; ניתוק שחקן → ספירה לאחור 20 שניות → הפסד אוטומטי + עדכון rating
6. כפתור ROOM — Create/Join/Cancel, מזהה חדר, המצטרף השני=יריב ושאר=צופים; לוגים בצד קליינט ושרת
