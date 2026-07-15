# שינויי מנוע ומשחקיות - 15.7.2026

מסמך זה מתעד את כל השינויים שנעשו היום במנוע/במודל התנועה בזמן אמת -
נפרד מ-`docs/interactive_view.md` (שמתעד את בניית ה-view הגרפי, נושא
אחר). לא נעשה כאן שום שינוי לוגיקה חדשה מעבר למה שמתואר - כל השינויים
עברו את מלוא חבילת הטסטים (222/222 עוברים בסוף היום).

## 1. מודל תנועה בזמן אמת חדש - כלי עוזב את הלוח מיד

**קבצים:** `realtime/motion.py`, `realtime/real_time_arbiter.py`, `engine/game_engine.py`.

### לפני
כלי שהתחיל לזוז נשאר פיזית על ה-`Board` בתא המקור שלו עד שההגעה
מתבצעת. תוצאה: כלי אויב שהגיע לתא המקור **תפס/ביטל** את התנועה
המקורית (כי `Board` עדיין "ראה" את הכלי הישן שם).

### עכשיו
- `RealTimeArbiter.start_motion` מסיר את הכלי מה-`Board` **מיידית**.
  הכלי חי רק כ-`Motion.piece` (שדה חדש - `Motion` שומר כלי מלא, לא רק
  `piece_id`) עד שהוא נוחת.
- כלי אויב שמגיע לתא המקור **לא** מבטל את התנועה - היא ממשיכה ליעדה
  המקורי. `GameEngine.request_move` חוסם רק כלי **מאותו צבע** מלהיכנס
  לתא-מקור של Motion פעיל (`friendly_departure_cell`); אויב יכול.
- **התנגשויות באוויר**: `Motion.path_cells()`/`time_at_cell()` מחשבים
  את התא המשותף המוקדם ביותר בין שתי תנועות פעילות, לפי **זמן הגעה
  בפועל** (לא סדר הכנסה, לא קצב פריימים):
  - אותו צבע: הראשון ממשיך; השני נעצר תא לפני נקודת המפגש
    (`Motion.truncate_before`).
  - צבעים שונים: מי שמגיע מאוחר יותר אוכל את מי שהגיע קודם, וממשיך
    ליעדו המקורי (עובר דרך נקודת ההתנגשות).
  - תיקו מדויק: אותו צבע → שניהם נעצרים; צבעים שונים → שניהם מוסרים
    (מדיניות מתועדת, אין "ראשון/שני" בתיקו אמיתי).
- `GameEngine.snapshot()` מוסיף כעת גם כלים "באוויר" (`arbiter.active_motions()`)
  לרשימת הכלים המוצגת - אחרת הם היו נעלמים לגמרי מה-render כל עוד הם
  לא על ה-`Board`.
- `is_position_busy` פושט: בודק רק `is_jumping_on` (לא `has_active_motion`
  יותר) - כלי שיושב כרגע בתא כלשהו אף פעם לא "תפוס" בגלל Motion ישן
  ולא-קשור שיצא מאותו תא בעבר.

### אימות חי (לא רק טסטים)
הרצתי תרחיש התנגשות-אוויר אמיתי (מסלולים מצטלבים, לא ליעד סופי משותף)
**דרך ה-pipeline הטקסטואלי המלא** (`python app.py` עם Board + כל
הפקודות בבום אחד ב-stdin): הכלי שהגיע ראשון לנקודת ההתנגשות נהרס
נכון, והמנצח המשיך **מעבר** לנקודת ההתנגשות ונחת ביעד המקורי שלו -
בדיוק כמו שהטסטים צופים. הלוח הלוגי לא נתקע ולא נשאר במצב לא-עקבי בשום
שלב, גם כשכל הפקודות מגיעות בבת אחת.

## 2. ביטול בחירה בלחיצה על יעד לא חוקי

**קובץ:** `input/controller.py` - `Controller._act_on_selection`.

לפני: יעד לא חוקי → הבחירה נשארת פתוחה, אפשר לנסות שוב עם אותו כלי.
עכשיו: כל תוצאה (הצלחה או כישלון) מנקה את הבחירה. יעד לא חוקי = חייבים
ללחוץ על הכלי מחדש כדי לבחור אותו.

## 3. JUMP דרך לחיצה ימנית ב-UI

**קבצים:** `view/click_router.py`, `view/run.py`.

`ClickRouter.jump(x, y)` מנתב לפי צבע הכלי בתא שנלחץ (כמו קליק ראשון
של מחווה), קורא ל-`Controller.jump()` של אותו controller. ב-`view/run.py`:
`cv2.EVENT_RBUTTONDOWN` → `router.jump(x, y)`, לצד `EVENT_LBUTTONDOWN`
→ `router.click(x, y)` הקיים.

## 4. State Machine למצבי אנימציה

**קובץ חדש:** `view/piece_state_machine.py` - `PieceStateMachine`.

מכונת מצבים מעל `AnimationState` (IDLE/MOVE/JUMP/LONG_REST/SHORT_REST)
שיושבת ב-**view בלבד** - לא נוגעת ב-`GameEngine`. המנוע ממשיך לדווח רק
IDLE/MOVE/JUMP; המכונה "שמה" LONG_REST/SHORT_REST כשהיא רואה מעבר
מ-MOVE/JUMP ל-IDLE, לפי `AnimationConfig.next_state_when_finished`
שכבר קיים ב-`config.json` של כל כלי ב-`pieces2` (וידאתי: `move→long_rest→idle`,
`jump→short_rest→idle`, עקבי בכל 12 הכלים). **זו אנימציה ויזואלית
בלבד** - לא קשורה למנגנון ה-cooldown החדש (סעיף הבא), שהוא כלל משחק
אמיתי במנוע.

## 5. COOLDOWN - הצטננות אחרי הליכה/קפיצה (חדש)

**קבצים:** `constants.py`, `realtime/real_time_arbiter.py`, `engine/game_engine.py`, `app.py`.

זהו, בניגוד לסעיף 4, **כלל משחק אמיתי** במנוע - לא רק ויזואלי: כלי
שסיים לנוע/לקפוץ **לא יכול לנוע או לקפוץ שוב** עד שתקופת המנוחה שלו
עוברת.

### קבועים חדשים (`constants.py`)
```python
LONG_REST_DURATION = 1500   # אחרי הליכה (move)
SHORT_REST_DURATION = 500   # אחרי קפיצה (jump)
```
מנוחה ארוכה יותר אחרי הליכה, קצרה יותר אחרי קפיצה - בדיוק כפי שביקשת.

### `RealTimeArbiter` - שדה ומתודות חדשים
- `_cooldowns: dict[piece_id, end_time]` - מתי כל כלי חופשי לפעול שוב.
- `is_resting(piece_id)` - בדיקת זמן טהורה (`clock < end_time`).
- `set_cooldown(piece_id, end_time)`.
- `active_jumps()` - חשיפה read-only, כדי ש-`GameEngine` ידע אילו jumps
  עומדים לפוג **לפני** ש-`advance_time` "בולע" אותם בשקט.

### `GameEngine` - מתי המנוחה מתחילה ואיפה נבדקת
- `request_move`/`request_jump`: בודקים `arbiter.is_resting(piece.id)` -
  אם כן, המהלך/הקפיצה נדחים (`MoveResult(False, "resting")` למהלך).
- `_advance`: לפני קריאה ל-`advance_time`, שומר אילו jumps עומדים לפוג
  עד הזמן החדש; אחרי הקריאה, מפעיל `SHORT_REST_DURATION` על הכלי שהיה
  בכל תא כזה.
- `_apply_events`: מפעיל `LONG_REST_DURATION` **רק** כשכלי באמת נוחת
  (אותה בדיקת זהות `moved.id == event.piece_id` שכבר קיימת שם עבור
  הכתרה) - כלי שמנצח התנגשות-אוויר וממשיך הלאה **לא** מקבל מנוחה
  באמצע, רק כשהוא באמת נוחת ביעדו האמיתי. וידאתי את זה בטסט ייעודי.
- `long_rest_duration`/`short_rest_duration` הם פרמטרים חדשים
  ל-`GameEngine.__init__` (מולאו). בשונה מ-`move_duration`/`jump_duration`,
  **מותר להם להיות 0** ("בלי cooldown") - זה ערך תקין וללא הבעיות
  שהיו ל-move/jump duration=0 בעבר.

### אימות חי (לא רק טסטים)
הרצתי תרחיש מלא **דרך ה-pipeline הטקסטואלי**: כלי זז, נוחת, מנסים
להזיז אותו שוב מיד - נדחה בשקט (נשאר במקום). מחכים 1500ms נוספים -
אותו מהלך בדיוק מצליח הפעם. בדיוק ההתנהגות המבוקשת.

## קבצים ששונו/נוספו היום - סיכום

| קובץ | סטטוס |
|---|---|
| `realtime/motion.py` | שונה - `Motion` שומר `piece` מלא, `path_cells`/`time_at_cell`/`truncate_before` |
| `realtime/real_time_arbiter.py` | שונה - מודל אירועים כרונולוגי, `is_resting`/`set_cooldown`/`active_jumps` |
| `engine/game_engine.py` | שונה - snapshot כולל כלים באוויר, בדיקות resting, cooldown ב-`_advance`/`_apply_events` |
| `input/controller.py` | שונה - ביטול בחירה ביעד לא חוקי |
| `constants.py` | שונה - `LONG_REST_DURATION`, `SHORT_REST_DURATION` |
| `app.py` | שונה - מזין את הקבועים החדשים ל-`GameEngine` |
| `view/click_router.py`, `view/run.py` | שונה - ניתוב `jump()` ל-לחיצה ימנית |
| `view/piece_state_machine.py` | חדש - State Machine ויזואלי |
| `tests/test_engine.py`, `tests/test_real_time_arbiter.py`, `tests/test_click_router.py` | שונה - עדכון טסטים ישנים + טסטים חדשים |
| `tests/test_piece_state_machine.py` | חדש |

## תוצאות

**222/222 טסטים עוברים.** כל שינוי בעל השפעה על טסטים קיימים אומת
בנפרד (הרצה עם השינוי מבוטל זמנית → הטסט נכשל → שחזור → הטסט עובר),
בנוסף לאימות חי דרך ה-pipeline הטקסטואלי המלא לשני התרחישים המרכזיים
(התנגשות אוויר, cooldown).
