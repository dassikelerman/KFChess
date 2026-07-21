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

## תזכורת: מפת הדרכים המלאה
1. ✅ BUS (Pub/Sub)
2. ✅ Client/Server מקומי + WebSocket
3. מסך Home + Login עם Username בלבד (shell, לא GUI); ראשון=White שני=Black
4. Login עם Username+Password (SQLite בצד שרת) + Rating (מתחיל 1200, ELO)
5. כפתור PLAY — matchmaking לפי ELO±100, MessageBox אם לא נמצא; ניתוק שחקן → ספירה לאחור 20 שניות → הפסד אוטומטי + עדכון rating
6. כפתור ROOM — Create/Join/Cancel, מזהה חדר, המצטרף השני=יריב ושאר=צופים; לוגים בצד קליינט ושרת
