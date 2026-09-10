# Match Series Data Model Enhancement

## Summary

This proposal adds explicit `MatchSeries` entities to the tournament data model. Currently, match series (best-of-N playoff matchups) are detected at runtime by grouping matches with same `(tour, bracket_slot, team_pair)`. The enhancement:

1. **Adds `MatchSeries` model** with team references preserving first-match order
2. **Adds nullable FK** from `Match` to `MatchSeries` (minimally invasive)
3. **Auto-detects existing series** via migration and `Match.save()` signal
4. **Enhances team/player history pages** with visual grouping for series matches
5. **Simplifies existing code** by replacing computed series logic with model queries

**Key Decision**: Series are auto-created when playoff matches are saved (no manual admin work required).

---

## Current State Analysis

### Existing Series Concept
Match series currently exist only as a **computed concept** in the codebase - they are not represented in the data model. The current detection logic groups matches by:
- Same `numb_tour` (tour round)
- Same `bracket_slot` (position in bracket)
- Same pair of teams (regardless of home/away)

### Where Series Are Currently Used

1. **Playoff Bracket Display** (`tournament_extras.py:498-548`)
   - `get_series_result()` - determines winner/loser of a completed series
   - `get_series_score()` - calculates aggregate score (by goals or match wins)
   - `BracketSlot` dataclass contains `matches` list for each slot

2. **Schedule Tab** (`tournament_schedule.html:47-104`)
   - `matches_by_bracket_slot` filter groups matches
   - Series displayed with header showing aggregate score + individual matches

3. **Match Detail Page** (`views.py:595-609`)
   - Queries series matches using `(numb_tour, bracket_slot, team_pair)`
   - Displays navigation buttons between matches in series

4. **Team Results Service** (`team_results.py:158-169`)
   - `_team_lost_series()` - determines if team lost series in DE bracket finals

### Problem: Team/Player History Pages
Matches in a series are displayed as **independent entries** with no visual grouping or cross-linking. This is the main UX gap.

---

## Proposed Data Model

### New Model: `MatchSeries`

```python
class MatchSeries(models.Model):
    """A series of matches between two teams in a playoff bracket slot."""
    
    class Meta:
        verbose_name = 'Серия матчей'
        verbose_name_plural = 'Серии матчей'
        unique_together = ('tour', 'bracket_slot')
        ordering = ['tour', 'bracket_slot']
    
    def __str__(self):
        return f'{self.team_home} vs {self.team_guest} ({self.tour})'
    
    # Core identifying fields
    tour = models.ForeignKey(
        'TourNumber',
        verbose_name='Тур',
        related_name='series',
        on_delete=models.CASCADE,
    )
    bracket_slot = models.PositiveSmallIntegerField(
        'Слот сетки',
        help_text='Номер слота в сетке ПО',
    )
    
    # Team references preserving the order from the first match in the series
    team_home = models.ForeignKey(
        'Team',
        verbose_name='Команда (верхняя строка)',
        related_name='home_series',
        on_delete=models.CASCADE,
    )
    team_guest = models.ForeignKey(
        'Team',
        verbose_name='Команда (нижняя строка)',
        related_name='guest_series',
        on_delete=models.CASCADE,
    )
```

### Modified Model: `Match`

```python
class Match(models.Model):
    # ... existing fields ...
    
    series = models.ForeignKey(
        'MatchSeries',
        verbose_name='Серия',
        related_name='matches',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text='Links match to its series (for playoff matches)',
    )
```

### Design Rationale

1. **Minimal Invasiveness**: Only adds one FK to Match (nullable), no changes to existing fields
2. **Team References**: `team_home`/`team_guest` on MatchSeries for:
   - Easy querying without joins
   - Display convenience (teams are always in same order in series)
   - **Preserves order from first match** (matches current `pairs_in_tour` behavior at line 378)
   - `team_home` = "top" team in bracket, `team_guest` = "bottom" team in bracket
3. **No Cached Scores**: Series score is computed on-the-fly via existing `get_series_score()` from individual match results and `PlayOffStage.winner_determinator`. Matches are prefetched anyway for display, so this is cheap and avoids sync complexity.
4. **Unique Constraint**: `(tour, bracket_slot)` ensures one series per bracket position
5. **Lookup `winner_determinator`**: Always from `PlayOffStage`, never cached on series

---

## Migration Strategy

### Detection Algorithm (Migration)

```python
def detect_match_series(apps, schema_editor):
    """Detect existing series from playoff matches during migration."""
    from collections import defaultdict
    
    Match = apps.get_model('tournament', 'Match')
    MatchSeries = apps.get_model('tournament', 'MatchSeries')
    
    # Group playoff matches by (tour, bracket_slot, team_pair)
    # Filter by bracket_slot > 0 (only playoff matches have this)
    playoff_matches = Match.objects.filter(
        bracket_slot__gt=0,
    ).select_related('numb_tour', 'team_home', 'team_guest').order_by('id')
    
    series_groups = defaultdict(list)
    for match in playoff_matches:
        # Use frozenset for grouping (order doesn't matter for grouping)
        pair = frozenset((match.team_home_id, match.team_guest_id))
        key = (match.numb_tour_id, match.bracket_slot, pair)
        series_groups[key].append(match)
    
    # Create MatchSeries for all groups (including single matches)
    created_count = 0
    for (tour_id, bracket_slot, _), matches in series_groups.items():
        # Preserve team order from FIRST match (matches sorted by id)
        first_match = matches[0]
        
        series = MatchSeries.objects.create(
            tour_id=tour_id,
            bracket_slot=bracket_slot,
            team_home_id=first_match.team_home_id,  # Top team in bracket
            team_guest_id=first_match.team_guest_id,  # Bottom team in bracket
        )
        
        # Link all matches to series
        Match.objects.filter(id__in=[m.id for m in matches]).update(series=series)
        created_count += 1
    
    return created_count
```

### Auto-Creation on Match Save

```python
# In tournament/models.py, add to Match class or as signal

@receiver(post_save, sender=Match)
def auto_create_series(sender, instance, **kwargs):
    """Auto-create/link series when saving playoff matches."""
    if not instance.bracket_slot or not instance.stage_id:
        return
    
    # Only for playoff stages
    from .models import PlayOffStage
    if not isinstance(instance.stage, PlayOffStage):
        return
    
    # Find existing series for this tour + bracket_slot
    series = MatchSeries.objects.filter(
        tour=instance.numb_tour,
        bracket_slot=instance.bracket_slot,
    ).first()
    
    if series is None:
        # Create new series - preserve team order from this first match
        series = MatchSeries.objects.create(
            tour=instance.numb_tour,
            bracket_slot=instance.bracket_slot,
            team_home=instance.team_home,  # Top team in bracket
            team_guest=instance.team_guest,  # Bottom team in bracket
        )
    
    # Link match to series if not already linked
    if instance.series_id != series.id:
        instance.series = series
        Match.objects.filter(id=instance.id).update(series=series)
```

### Migration File Structure

```python
# 0046_matchseries.py

from django.db import migrations, models
import django.db.models.deletion

def create_match_series(apps, schema_editor):
    """Create MatchSeries from existing playoff matches."""
    # ... detection algorithm above ...

def reverse_migration(apps, schema_editor):
    """Remove all MatchSeries (matches keep their data)."""
    MatchSeries = apps.get_model('tournament', 'MatchSeries')
    MatchSeries.objects.all().delete()

class Migration(migrations.Migration):
    dependencies = [
        ('tournament', '0045_alter_medaltype_category_alter_medaltype_image'),
    ]

    operations = [
        # Step 1: Create MatchSeries model
        migrations.CreateModel(
            name='MatchSeries',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('bracket_slot', models.PositiveSmallIntegerField(verbose_name='Слот сетки')),
                ('team_home', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='home_series', to='tournament.team', verbose_name='Команда (верхняя строка)')),
                ('team_guest', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='guest_series', to='tournament.team', verbose_name='Команда (нижняя строка)')),
                ('tour', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='series', to='tournament.tournumber', verbose_name='Тур')),
            ],
            options={
                'verbose_name': 'Серия матчей',
                'verbose_name_plural': 'Серии матчей',
                'unique_together': {('tour', 'bracket_slot')},
            },
        ),
        
        # Step 2: Add series FK to Match
        migrations.AddField(
            model_name='match',
            name='series',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='matches',
                to='tournament.matchseries',
                verbose_name='Серия',
            ),
        ),
        
        # Step 3: Populate series from existing data
        migrations.RunPython(create_match_series, reverse_migration),
    ]
```

---

## Units of Work

### 1. Data Model & Migration (Core)
- [ ] Create `MatchSeries` model in `tournament/models.py`
- [ ] Add `series` FK to `Match` model
- [ ] Create migration `0046_matchseries.py` with:
  - Model creation
  - FK addition
  - `RunPython` to detect and populate series
- [ ] Add `MatchSeries` to `tournament/admin.py`
- [ ] Update `MatchAdmin` to show/filter by series

### 2. Series Score Update Logic
- [ ] Keep using existing `get_series_score()` computed from individual match results on-the-fly
- [ ] No cached score fields needed - matches are prefetched for display anyway
- [ ] Verify existing `get_series_result()` / `get_series_score()` template tags work with model-based series

### 3. Playoff Bracket Optimization
- [ ] Update `BracketSlot` dataclass to use `MatchSeries` instead of computing
- [ ] Simplify `get_series_result()` and `get_series_score()` template tags
- [ ] Update `playoff_bracket.html` to use series data directly
- [ ] Remove redundant `matches_by_bracket_slot` filter (or keep for backwards compat)

### 4. Schedule Tab Optimization
- [ ] Update `tournament_schedule.html` to query `MatchSeries` directly
- [ ] Simplify `tour-series` partial to use series model
- [ ] Keep visual appearance identical

### 5. Match Detail Page
- [ ] Update `MatchDetail.get_context_data()` to use `match.series`
- [ ] Simplify series matches query to `match.series.matches.all()`
- [ ] Keep navigation buttons behavior identical

### 6. Team History Page Enhancement (New Feature)
- [ ] Update `team_seasons` template tag to prefetch series
- [ ] Modify `team_matches.html` to group matches by series
- [ ] Add visual grouping for series (card with left border, similar to schedule tab)
- [ ] Add navigation links between matches in same series (numbered buttons)
- [ ] Display series aggregate score in group header
- [ ] Keep individual match cards within the group

**Visual Design:**
```
┌─ Series: Team A vs Team B (Aggregate: 4:2) ──────────────┐
│  [1 матч] [2 матч] [3 матч]                              │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ Match 1: Team A 2:1 Team B  │  В  │                │  │
│  └─────────────────────────────────────────────────────┘  │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ Match 2: Team B 1:2 Team A  │  В  │                │  │
│  └─────────────────────────────────────────────────────┘  │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ Match 3: Team A 0:1 Team B  │  П  │                │  │
│  └─────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────┘
```

### 7. Player History Page Enhancement (New Feature)
- [ ] Update `player_seasons` template tag to prefetch series
- [ ] Modify `player_matches.html` to group matches by series
- [ ] Apply same visual treatment as team history page
- [ ] Ensure player stats (goals, assists) still display correctly
- [ ] Show player's team in series header for clarity

### 8. Team Results Service Update
- [ ] Update `_team_lost_series()` to use `MatchSeries.matches` grouping instead of computing series matches manually
- [ ] Series winner is determined via existing `get_series_result()` logic (no cached `winner` field)
- [ ] Verify DE bracket placement inference still works correctly

---

## Out of Scope (Per Requirements)

### Host Reservations
- Each match in series can be booked independently
- No changes to `reservation` app needed
- Different matches may be played in different rooms

### Predictions & Fantasy League
- These only work with single-stage tournaments (round-robin)
- Playoff series cannot exist in these tournaments
- No changes needed to `predictions` or `fantasy_league` apps

---

## Visual Grouping Implementation Details

### Template Structure for Series in History Pages

```django
{# In team_matches.html or player_matches.html #}

{% if match.series %}
  {# First match in series - render group header #}
  {% ifchanged match.series %}
    <div class="series-group tw:border-l-4 tw:border-primary tw:pl-4 tw:mb-4">
      {# Series title and aggregate score #}
      {% get_series_score match.series.team_home match.series.team_guest match.series.matches.all match.series.tour.stage as series_score %}
      <div class="series-header tw:flex tw:items-center tw:gap-2 tw:mb-2">
        <span class="tw:font-semibold tw:text-primary">Серия</span>
        <span class="tw:text-sm tw:text-base-content/70">
          {{ match.series.team_home.title }} vs {{ match.series.team_guest.title }}
        </span>
        {% if match.series.matches.count > 1 %}
          <span class="tw:ml-auto tw:text-sm tw:font-semibold">
            {% if series_score %}
              {{ series_score.team1_score }} : {{ series_score.team2_score }}
            {% else %}
              vs
            {% endif %}
          </span>
        {% endif %}
      </div>
      
      {# Navigation buttons (only when series has more than 1 match) #}
      {% if match.series.matches.count > 1 %}
        <div class="series-nav tw:flex tw:gap-1 tw:mb-2">
          {% for series_match in match.series.matches.all %}
            <a href="{{ series_match.get_absolute_url }}" 
               class="tw:btn tw:btn-xs {% if series_match == match %}tw:btn-primary{% else %}tw:btn-outline{% endif %}">
              {{ forloop.counter }} матч
            </a>
          {% endfor %}
        </div>
      {% endif %}
  {% endifchanged %}
  
  {# Individual match card (nested inside series-group) #}
  <div class="series-match tw:ml-4">
    ... existing match card markup ...
  </div>
  
  {# Close series group after last match #}
  {% ifchanged match.series %}{% else %}
    {% if forloop.last %}</div>{% endif %}
  {% endifchanged %}
  
{% else %}
  {# Regular match without series - render normally #}
  ... existing match card markup ...
{% endif %}
```

### CSS Styling

```css
/* Series group styling */
.series-group {
  background: linear-gradient(135deg, oklch(var(--p) / 0.03) 0%, transparent 100%);
  border-radius: var(--rounded-box, 1rem);
  padding: 0.75rem;
}

.series-header {
  font-size: 0.875rem;
}

.series-match {
  opacity: 0.95;
}

.series-match:hover {
  opacity: 1;
}
```

### Template Tag for Series Grouping

```python
# In tournament_extras.py

@register.filter
def group_by_series(matches):
    """Group matches by series, keeping order."""
    result = []
    current_series = None
    series_matches = []
    
    for match in matches:
        if match.series_id != current_series:
            if series_matches:
                result.append(('series', current_series, series_matches))
            current_series = match.series_id
            series_matches = [match]
        else:
            series_matches.append(match)
    
    if series_matches:
        result.append(('series', current_series, series_matches))
    
    return result
```

---

## Additional Notes

### Data Integrity Considerations

1. **Existing Single Matches**: Matches with `bracket_slot=0` or in non-playoff stages won't have series. This is correct behavior.

2. **Series Consistency**: The `unique_together` constraint on `(tour, bracket_slot)` prevents duplicate series.

3. **Orphaned Matches**: If a match is moved/edited, the series FK should be updated or cleared.

### Performance Considerations

1. **Prefetching**: Template tags should use `prefetch_related('series')` to avoid N+1 queries.

2. **Denormalized Scores**: Cached `team1_score`/`team2_score` avoid recalculating on every page load.

3. **Index**: Add index on `Match.series_id` for efficient lookups.

### Future Extensibility

1. **Regular Season Series**: Model could be extended for regular season rematches (e.g., "autumn spring" format).

2. **Best-of-N Configuration**: Could add `best_of` field to MatchSeries if needed.

3. **Series Metadata**: Could add `started_at`, `completed_at` timestamps for analytics.

---

## Series Creation Approach: Hybrid (Recommended)

### Analysis of Match Creation Workflows

1. **Regular Season**: Created via `create_schedule` management command (round-robin). These never have `bracket_slot > 0`, so no series needed.

2. **Playoff Matches**: Created **individually in admin**. There's no batch creation for playoffs.

### Recommended Approach: Auto-Detection + Migration

**For Existing Data:**
- Migration script detects series by grouping `(tour, bracket_slot, team_pair)`
- Creates `MatchSeries` and links matches

**For New Matches:**
- Override `Match.save()` to auto-detect series
- When saving a playoff match with `bracket_slot > 0`:
  1. Query for other matches in same `(tour, bracket_slot)` with same team pair
  2. If found: link to existing series (create if needed)
  3. If not found: create series proactively (will be linked when 2nd match added)

**Admin Integration:**
- Add `MatchSeries` to admin as **read-only** for visibility
- Show series FK on Match form as **read-only** (auto-managed)
- Optionally: Add "Regenerate Series" action for bulk operations

### Why This Works

1. **No Admin Burden**: Admins don't need to manually create series
2. **Automatic**: Series appear as soon as 2nd match is added to same slot
3. **Visible**: Admin can see all series and their matches
4. **Backwards Compatible**: Existing matches get linked via migration

### Edge Cases

1. **Single-Match Slots**: Series is created even for single matches, but **displayed as single match** (current behavior preserved). This ensures:
   - Consistent data model (every playoff slot has a series)
   - Easy future extension if more matches are added
   - Bracket stubs work correctly
2. **Match Deletion**: When a match is deleted, series remains (can be cleaned up via management command)
3. **Match Moves**: If a match is moved to different slot, series link is updated

---

## Decisions (Confirmed)

1. **Single-match series**: Create series for all playoff slots (even single matches), but display as single match everywhere (current behavior preserved).

2. **`winner_determinator` lookup**: Always look up from `PlayOffStage` at runtime. Do NOT cache on series.

3. **No cached score fields**: Drop `team1_score`/`team2_score` from series. Scores computed on-the-fly via existing `get_series_score()` template tag, since matches are prefetched for display anyway. Also removes naming inconsistency with `team_home`/`team_guest`.

4. **Implementation order**: Migration/data model first, then UI enhancements.

5. **Team ordering**: Preserve order from the **first match** in the series, matching current `pairs_in_tour` behavior (`matches[0].team_home`, `matches[0].team_guest`). Do NOT sort by team ID.

6. **Technical Defeats**: Treated as regular win/loss for series purposes (existing behavior preserved).
