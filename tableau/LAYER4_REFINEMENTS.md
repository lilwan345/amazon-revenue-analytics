# Layer 4 — Dashboard refinement checklist (v1 → v2)

> Goal: close the gap between the live v1 dashboard and the static mockup in
> `outputs/figures/layer4/dashboard_mockup.png`. **4 high-impact + 3 optional** items;
> all are visual polish — the structure and data are correct.
>
> Workflow: open the workbook in **Tableau Desktop** → apply the items below →
> **File → Save to Tableau Public** (overwrites the same URL). Each item lists the
> exact Tableau click-path. Field names use Tableau's auto-capitalised display
> form (e.g. CSV column `over_index_pct` → field "Over Index Pct").
>
> Reference (live v1):
> https://public.tableau.com/app/profile/leo.wan3084/viz/AmazonFinanceReviewDashboardQ32022/Dashboard1

---

## Priority 1 — lands the 30-second story

### ☐ 1. Add a "so what" caption under every panel
On the **dashboard**, drag a **Text** object from the left Objects pane to the area
directly under each sheet, then paste the matching caption. Format each text object:
**italic, 9.5 pt, color `#555555`**.

| Panel | Caption (paste verbatim) |
|---|---|
| Concentration | `So what: concentration sits at the top — but the long tail still matters (top 20% = 55%, not 80%).` |
| Over-Index | `So what: heavy cadence (>10×/mo) over-indexes +387% — engagement, not affluence, defines the top decile.` |
| RaR by Decile | `So what: revenue is at the top, but risk is in the middle — mid-deciles 6–9 carry 65% of RaR on 13% of GMV.` |
| Scale × Growth | `So what: Home & H&PC are the cleanest INVEST — high growth that new customers actually enter through.` |

### ☐ 2. Label every bubble on the Scale × Growth scatter
Open the **Scale × Growth** worksheet → Data pane → drag **Super Category** onto the
**Label** shelf in the Marks card. Click **Label** → set alignment **Center**, font
**7.5–8 pt**, color `#2c3e50`. (Tooltip already carries the full info; the label is
for at-a-glance readability.)

### ☐ 3. Show "+387%"-style inline labels on the Over-Index bars
Open the **Over-Index** worksheet → drag **Over Index Pct** onto the **Label** shelf
in the Marks card → click that pill → **Format → Numbers → Custom** → enter
`+#,##0"%"`. Set Label alignment **End of bar**, font 8.5 pt, color `#2c3e50`. Bars
will now display `+387%`, `+154%`, etc.

### ☐ 4. Hide the internal calc-field legends on the dashboard
Back on the **dashboard**, find the two legend cards on the right that read
**"Top driver — False / True"** and **"Mid-tier — False / True"**. These are
internal calc fields whose meaning is already conveyed by color. Click the small
**X** on each card (or right-click → **Remove from Dashboard**).
Keep the **Quadrant** legend (meaningful) and optionally the **N Households**
size legend.

---

## Priority 2 — optional polish

### ☐ 5. Annotate the headline finding on the Concentration panel
Open the **Concentration** worksheet → right-click a point on the Lorenz curve near
the upper-right (around 90% population) → **Annotate → Point**. Replace the default
text with:

`Top decile = 36.2% of GMV  ·  Gini = 0.529`

Format: 9 pt, color `#c0392b` (red accent), light arrow.

### ☐ 6. Add a subtitle under the dashboard title
On the **dashboard**, double-click the title text object and append a second line
below the main title (or add a separate Text object directly under it):

`Finance Review Dashboard  ·  Q3 2022 Snapshot  ·  2,846 U.S. households (consenting panel)`

Format the subtitle: 10 pt, color `#7f8c8d` (muted gray), not bold.

### ☐ 7. Rename the dashboard tab for a cleaner URL slug *(cosmetic)*
At the bottom tab strip in Tableau Desktop, right-click the **"Dashboard 1"** tab →
**Rename Dashboard** → enter `FinanceReview` (no spaces). On re-publish, the URL
slug becomes `…/viz/AmazonFinanceReviewDashboardQ32022/FinanceReview`.
*If you do this, ping me to update the 3 URL references in README.md +
LAYER4_BUILD_GUIDE.md* — otherwise leave it.

---

## Re-publish

**File → Save to Tableau Public** → keep the same workbook name
(`AmazonFinanceReviewDashboardQ32022`) → it overwrites the existing public viz at
the same URL. No README changes needed (unless you did item 7).

When done, mark the checkboxes above and (optionally) `git add` + commit this file
as a record of v2 having landed.

---

## Reference: palette + style (matches `src/viz_utils.py`)

| Role | Hex |
|---|---|
| Primary data | `#1f4e79` |
| Accent / highlight | `#c0392b` |
| Reference line / muted | `#7f8c8d` |
| Light axis / grid | `#cccccc` |
| Text labels | `#2c3e50` |
| Caption color | `#555555` |
