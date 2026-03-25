(function () {
  if (window.__commentsReactionsInitialized) {
    return;
  }
  window.__commentsReactionsInitialized = true;

  const asset = function (path) {
    const popover = document.getElementById('comments-reactions-popover');
    const staticUrl = popover?.dataset?.commentsReactionsStaticUrl || '/static/';
    const normalizedBase = staticUrl.endsWith('/') ? staticUrl : `${staticUrl}/`;
    const normalizedPath = path.startsWith('/') ? path.slice(1) : path;
    return `${normalizedBase}${normalizedPath}`;
  };

  const initCommentsReactions = function () {
    const popover = document.getElementById('comments-reactions-popover');
    const mount = popover && popover.querySelector('[data-comments-emoji-mart]');
    if (!popover || !mount) {
      return;
    }

    let activeRoot = null;
    let activeToggle = null;
    let picker = null;
    let isPopoverOpen = false;
    const DARK_THEMES = new Set([
      'dark',
      'halloween',
      'forest',
      'luxury',
      'dracula',
      'business',
      'night',
      'coffee',
      'dim',
      'sunset',
    ]);

    const getPickerTheme = function () {
      return DARK_THEMES.has(document.body?.dataset?.theme) ? 'dark' : 'light';
    };

    const ensurePicker = function () {
      if (picker) {
        return;
      }

      const Picker = window.EmojiMart?.Picker;
      if (!Picker) {
        mount.textContent = 'Не удалось загрузить EmojiMart';
        return;
      }

      const customEmojis = [
        {
          id: 'cishaxball',
          name: 'CIS-HAXBALL',
          emojis: [
            {
              id: 'cishaxball',
              name: 'CIS-HAXBALL',
              keywords: ['cis', 'cishaxball'],
              skins: [{ src: asset('img/emoji/cishaxball.png') }],
            },
            {
              id: 'iks',
              name: 'iks',
              keywords: ['iks', 'mas'],
              skins: [{ src: asset('img/emoji/iks.png') }],
            },
            {
              id: 'wenamka',
              name: 'Wenamka',
              keywords: ['wenamka', 'wenam', 'wenom'],
              skins: [{ src: asset('img/emoji/wenamka.png') }],
            },
            {
              id: 'verty',
              name: 'Verty',
              keywords: ['verty'],
              skins: [{ src: asset('img/emoji/verty.png') }],
            },
            {
              id: 'mokujin',
              name: 'Shalin',
              keywords: ['mok', 'mokujin', 'shalin'],
              skins: [{ src: asset('img/emoji/mok.png') }],
            },

            {
              id: 'bad_clowns',
              name: 'BAD CLOWNS',
              keywords: ['bad', 'clown'],
              skins: [{ src: asset('img/emoji/teams/bad_clowns.png') }],
            },
            {
              id: 'fcu',
              name: 'FC United',
              keywords: ['fcu', 'united'],
              skins: [{ src: asset('img/emoji/teams/fcunited.png') }],
            },
            {
              id: 'kumys',
              name: 'KUMYS POWER',
              keywords: ['kumys', 'power'],
              skins: [{ src: asset('img/emoji/teams/kumys.png') }],
            },
            {
              id: 'legendary_stars',
              name: 'Legendary Stars',
              keywords: ['ls', 'legend', 'star'],
              skins: [{ src: asset('img/emoji/teams/ls.png') }],
            },
            {
              id: 'bloodstream',
              name: 'Bloodstream',
              keywords: ['blood', 'bs'],
              skins: [{ src: asset('img/emoji/teams/bloodstream.png') }],
            },
            {
              id: '7up',
              name: '7up',
              keywords: ['7up'],
              skins: [{ src: asset('img/emoji/teams/7up.png') }],
            },
            {
              id: 'water_heroes',
              name: 'Water Heroes',
              keywords: ['water', 'hero', 'hat'],
              skins: [{ src: asset('img/emoji/teams/water-heroes.png') }],
            },
            {
              id: 'hunterxhunter',
              name: 'Hunter x Hunter',
              keywords: ['hunter', 'x'],
              skins: [{ src: asset('img/emoji/teams/hunterxhunter.png') }],
            },
            {
              id: 'hello_kitty',
              name: 'Hello Kitty',
              keywords: ['hello', 'kitty', 'kissonya'],
              skins: [{ src: asset('img/emoji/teams/kitty.png') }],
            },
            {
              id: 'viollet_team',
              name: 'Viollet Team',
              keywords: ['viollet', 'timoxa', '196'],
              skins: [{ src: asset('img/emoji/teams/viollet.png') }],
            },
            
            {
              id: 'aces',
              name: 'ACES',
              keywords: ['aces'],
              skins: [{ src: asset('img/emoji/teams/aces.png') }],
            },
            {
              id: 'vyazka-mol',
              name: 'vyazka-mol',
              keywords: ['vyazka', 'mol', 'karpen', 'larin'],
              skins: [{ src: asset('img/emoji/teams/vyazka-mol.png') }],
            },
            {
              id: 'adhd',
              name: 'adhd',
              keywords: ['adhd'],
              skins: [{ src: asset('img/emoji/teams/adhd.png') }],
            },
            {
              id: 'kaksobaki',
              name: 'На вид как собаки',
              keywords: ['kak', 'sobaki', 'dog'],
              skins: [{ src: asset('img/emoji/teams/sobaki.png') }],
            },
            {
              id: 'twd',
              name: 'The Walking Dead',
              keywords: ['twd', 'walking', 'dead', 'zombie'],
              skins: [{ src: asset('img/emoji/teams/twd.png') }],
            },
            {
              id: 'gazzaevpes',
              name: 'ГАЗЗАЕВПЁС МОСКВА',
              keywords: ['gaz', 'gazaev', 'pes'],
              skins: [{ src: asset('img/emoji/teams/gazzaevpes.png') }],
            },
            {
              id: 'brateki',
              name: 'Братеки',
              keywords: ['brat', 'brateki', 'skyred'],
              skins: [{ src: asset('img/emoji/teams/brateki.png') }],
            },
            {
              id: 'ubers',
              name: 'UBERS',
              keywords: ['ubers'],
              skins: [{ src: asset('img/emoji/teams/ubers.png') }],
            },

            {
              id: 'rockets',
              name: 'Rockets',
              keywords: ['rocket'],
              skins: [{ src: asset('img/emoji/teams/rockets.png') }],
            },
            {
              id: 'bloodstream_young',
              name: 'Bloodstream Young',
              keywords: ['blood', 'young', 'bsy'],
              skins: [{ src: asset('img/emoji/teams/bloodstream-young.png') }],
            },
            {
              id: 'edelweiss',
              name: 'edelweiss',
              keywords: ['edelweiss'],
              skins: [{ src: asset('img/emoji/teams/edelweiss.png') }],
            },
            {
              id: 'fc6',
              name: 'FC6',
              keywords: ['fc6'],
              skins: [{ src: asset('img/emoji/teams/fc6.png') }],
            },
            {
              id: 'galaxy_united',
              name: 'Galaxy United',
              keywords: ['galaxy', 'united'],
              skins: [{ src: asset('img/emoji/teams/galaxy.png') }],
            },
            {
              id: 'platina',
              name: 'HC Platina',
              keywords: ['platina'],
              skins: [{ src: asset('img/emoji/teams/Platina.png') }],
            },
            {
              id: 'shaika04',
              name: 'Шайка-04',
              keywords: ['shaika', '04'],
              skins: [{ src: asset('img/emoji/teams/shaika.png') }],
            },
            {
              id: 'hc_summer_rain',
              name: 'ХК Летний Дождик',
              keywords: ['summer', 'rain', 'hcsr'],
              skins: [{ src: asset('img/emoji/teams/summer-rain.png') }],
            },
            {
              id: 'age_of_kings',
              name: 'The Age of Kings',
              keywords: ['age', 'king', 'tak', 'taok'],
              skins: [{ src: asset('img/emoji/teams/the_age_of_kings.png') }],
            },
            {
              id: 'farma',
              name: 'Real Pharma',
              keywords: ['farma', 'real', 'pharma'],
              skins: [{ src: asset('img/emoji/teams/farma.png') }],
            },

            {
              id: 'beatles',
              name: 'The Beatles',
              keywords: ['beatles'],
              skins: [{ src: asset('img/emoji/teams/Beatles.png') }],
            },
            {
              id: 'bounty',
              name: 'Bounty',
              keywords: ['Bounty'],
              skins: [{ src: asset('img/emoji/teams/Bounty.png') }],
            },
            {
              id: 'flhax',
              name: 'FLHAX.FUN',
              keywords: ['flhax'],
              skins: [{ src: asset('img/emoji/teams/Flhax.png') }],
            },
            {
              id: 'the_evil_agents',
              name: 'The Evil Agents',
              keywords: ['tea', 'evil', 'agent'],
              skins: [{ src: asset('img/emoji/teams/TEA.png') }],
            },
            {
              id: 'two_z',
              name: 'Two-Z',
              keywords: ['two', 'z'],
              skins: [{ src: asset('img/emoji/teams/Two-z.png') }],
            },
            {
              id: 'angry_beavers',
              name: 'Злые Бобры',
              keywords: ['angry', 'beaver'],
              skins: [{ src: asset('img/emoji/teams/angry-beavers.png') }],
            },
            {
              id: 'anji',
              name: 'Anji',
              keywords: ['anji'],
              skins: [{ src: asset('img/emoji/teams/anji.png') }],
            },
            {
              id: 'anubis',
              name: 'Anubis',
              keywords: ['anubis'],
              skins: [{ src: asset('img/emoji/teams/anubis.png') }],
            },
            {
              id: 'atlanta',
              name: 'Атланта Хоукс',
              keywords: ['atlanta', 'hawk'],
              skins: [{ src: asset('img/emoji/teams/atlanta.png') }],
            },
            {
              id: 'black_leo',
              name: 'Balck Leopards',
              keywords: ['black', 'leo', 'zubus'],
              skins: [{ src: asset('img/emoji/teams/black-leo.png') }],
            },
            {
              id: 'bm',
              name: 'Bastard München',
              keywords: ['bm', 'bastard', 'munchen'],
              skins: [{ src: asset('img/emoji/teams/bm.png') }],
            },
            {
              id: 'bolich',
              name: 'Bolich',
              keywords: ['bolich'],
              skins: [{ src: asset('img/emoji/teams/bolich.png') }],
            },
            {
              id: 'chertanovo',
              name: 'ХК Чертаново 2012',
              keywords: ['chertanovo', '2012'],
              skins: [{ src: asset('img/emoji/teams/chertanovo.png') }],
            },
            {
              id: 'chertanovo_2013',
              name: 'ХК Чертаново 2013',
              keywords: ['chertanovo', '2013'],
              skins: [{ src: asset('img/emoji/teams/chertanovo2013.png') }],
            },
            {
              id: 'clasha',
              name: 'Team Clasha',
              keywords: ['clasha'],
              skins: [{ src: asset('img/emoji/teams/clasha.png') }],
            },
            {
              id: 'everton',
              name: 'Everton',
              keywords: ['everton'],
              skins: [{ src: asset('img/emoji/teams/everton.png') }],
            },
            {
              id: 'fcu2',
              name: 'FC United 2',
              keywords: ['fcu', 'united'],
              skins: [{ src: asset('img/emoji/teams/fcu-2.png') }],
            },
            {
              id: 'freak_circus',
              name: 'Freak Circus',
              keywords: ['freak', 'circus'],
              skins: [{ src: asset('img/emoji/teams/freak-circus.png') }],
            },
            {
              id: 'pokolenie_chudes',
              name: 'Поколение Чудес',
              keywords: ['pokolenie', 'generation', 'miracle'],
              skins: [{ src: asset('img/emoji/teams/generation-of-miracles.png') }],
            },
            {
              id: 'hc_glass',
              name: 'HC Glass',
              keywords: ['glass'],
              skins: [{ src: asset('img/emoji/teams/glass.png') }],
            },
            {
              id: 'gomofoby',
              name: 'Гомофобы',
              keywords: ['gomofoby', 'gay'],
              skins: [{ src: asset('img/emoji/teams/gomofoby.png') }],
            },
            {
              id: 'greenland',
              name: 'GreenLand',
              keywords: ['greenland', 'iks', 'mas'],
              skins: [{ src: asset('img/emoji/teams/greenland.png') }],
            },
            {
              id: 'grusteam',
              name: 'Grusteam',
              keywords: ['grusteam'],
              skins: [{ src: asset('img/emoji/teams/grusteam.png') }],
            },
            {
              id: 'gsw',
              name: 'Golden State Warriors',
              keywords: ['gsw', 'goladen', 'state', 'warrior'],
              skins: [{ src: asset('img/emoji/teams/gsw.png') }],
            },
            {
              id: 'gucci_gang',
              name: 'GUCCI GANG',
              keywords: ['gucci', 'gang'],
              skins: [{ src: asset('img/emoji/teams/gucci.png') }],
            },
            {
              id: 'homyaki',
              name: 'Хомяки',
              keywords: ['homyaki', 'hamster', 'verty'],
              skins: [{ src: asset('img/emoji/teams/hamsters.png') }],
            },
            {
              id: 'idm',
              name: 'IDM',
              keywords: ['idm'],
              skins: [{ src: asset('img/emoji/teams/idm.png') }],
            },
            {
              id: 'kalich',
              name: 'Kalich Gaming',
              keywords: ['kalich', 'gaming'],
              skins: [{ src: asset('img/emoji/teams/kalich.png') }],
            },
            {
              id: 'medvjedi',
              name: 'Medvjedi',
              keywords: ['medvjedi', 'wenam', 'wenom'],
              skins: [{ src: asset('img/emoji/teams/medvjedi.png') }],
            },
            {
              id: 'metallurg',
              name: 'Metallurg',
              keywords: ['metallurg'],
              skins: [{ src: asset('img/emoji/teams/metallurg.png') }],
            },
            {
              id: 'miami_mmb',
              name: 'FC Miami Mamoball',
              keywords: ['miami', 'mmb', 'mamoball'],
              skins: [{ src: asset('img/emoji/teams/miami-mmb.png') }],
            },
            {
              id: 'monkey_business',
              name: 'Monkey Business',
              keywords: ['monkey-business', 'monkey', 'business'],
              skins: [{ src: asset('img/emoji/teams/monkey-business.png') }],
            },
            {
              id: 'moon_lovers',
              name: 'Moon Lovers',
              keywords: ['moon', 'lover'],
              skins: [{ src: asset('img/emoji/teams/moon-lovers.png') }],
            },
            {
              id: 'morgen',
              name: 'Morgenshtern Team',
              keywords: ['morgen'],
              skins: [{ src: asset('img/emoji/teams/morgen.png') }],
            },
            {
              id: 'nostuff',
              name: 'NoStuff',
              keywords: ['nostuff', 'jora', 'young'],
              skins: [{ src: asset('img/emoji/teams/nostuff.png') }],
            },
            {
              id: 'omp',
              name: 'One more pass',
              keywords: ['omp', 'one', 'more', 'pass', 'iks', 'mas'],
              skins: [{ src: asset('img/emoji/teams/omp.png') }],
            },
            {
              id: 'orlando_pirates',
              name: 'HC Orlando Pirates',
              keywords: ['orlando', 'pirate'],
              skins: [{ src: asset('img/emoji/teams/orlando.png') }],
            },
            {
              id: 'oxxy',
              name: 'Оксидиум',
              keywords: ['oxy', 'oxxy'],
              skins: [{ src: asset('img/emoji/teams/oxy.png') }],
            },
            {
              id: 'pechnegi',
              name: 'Печенеги',
              keywords: ['pechnegi', 'cookie'],
              skins: [{ src: asset('img/emoji/teams/pechnegi.png') }],
            },
            {
              id: 'pornhub',
              name: 'Pornhub',
              keywords: ['pornhub', 'porn', 'hub', 'ph'],
              skins: [{ src: asset('img/emoji/teams/pornhub.png') }],
            },
            {
              id: 'qwerty',
              name: 'qwerty',
              keywords: ['qwerty'],
              skins: [{ src: asset('img/emoji/teams/qwerty.png') }],
            },
            {
              id: 'skyred',
              name: 'SkyRed',
              keywords: ['skyred'],
              skins: [{ src: asset('img/emoji/teams/skyred.png') }],
            },
            {
              id: 'smurfiki',
              name: 'Smurfiki',
              keywords: ['smurf'],
              skins: [{ src: asset('img/emoji/teams/smurfiki.png') }],
            },
            {
              id: 'soez',
              name: 'So EZ',
              keywords: ['soez', 'ez', 'easy', 'nick'],
              skins: [{ src: asset('img/emoji/teams/soez.png') }],
            },
            {
              id: 'deti_solntsa',
              name: 'Дети Солнца',
              keywords: ['sun', 'children', 'ds', 'deti'],
              skins: [{ src: asset('img/emoji/teams/sun-children.png') }],
            },
            {
              id: 'tatarstan',
              name: 'AS Tatarstan',
              keywords: ['ast', 'tatar'],
              skins: [{ src: asset('img/emoji/teams/tatarstan.png') }],
            },
            {
              id: 'tiktok_house',
              name: 'TikTok House',
              keywords: ['tiktok', 'house'],
              skins: [{ src: asset('img/emoji/teams/tiktok.png') }],
            },
            {
              id: 'tld',
              name: 'The Last Dance',
              keywords: ['tld', 'last', 'dance'],
              skins: [{ src: asset('img/emoji/teams/tld.png') }],
            },
            {
              id: 'vision_sun',
              name: 'Vision Sun',
              keywords: ['vision', 'sun'],
              skins: [{ src: asset('img/emoji/teams/vision-sun.png') }],
            },
            {
              id: 'vyazka',
              name: 'vyazka',
              keywords: ['vyazka', 'karpen', 'larin'],
              skins: [{ src: asset('img/emoji/teams/vyazka.png') }],
            },
            {
              id: 'warriors',
              name: 'Warriors',
              keywords: ['warrior'],
              skins: [{ src: asset('img/emoji/teams/warriors.png') }],
            },
            {
              id: 'kvadrat',
              name: 'квадрат',
              keywords: ['kvadrat', 'k2'],
              skins: [{ src: asset('img/emoji/teams/квадрат.png') }],
            },
          ],
        },
      ];

      const customCategoryIcons = {
        cishaxball: {
          src: asset('img/emoji/cishaxball.png'),
        },
      };

      picker = new Picker({
        locale: 'ru',
        previewPosition: 'bottom',
        searchPosition: 'sticky',
        theme: getPickerTheme(),
        perLine: 8,
        maxFrequentRows: 2,
        custom: customEmojis,
        categoryIcons: customCategoryIcons,
        onEmojiSelect: function (emoji) {
          if (!activeRoot || !window.htmx) {
            return;
          }

          popover.hidePopover();
          window.htmx.ajax('POST', activeRoot.dataset.reactionsUrl, {
            source: activeRoot,
            target: activeRoot.dataset.commentTarget,
            swap: 'outerHTML',
            values: {
              emoji_id: emoji?.id || '',
              emoji_native: emoji?.native || '',
              emoji_src: emoji?.src || '',
              emoji_name: emoji?.name || '',
              emoji_shortcodes: Array.isArray(emoji?.shortcodes) ? emoji.shortcodes.join(',') : (emoji?.shortcodes || ''),
              emoji_keywords: JSON.stringify(Array.isArray(emoji?.keywords) ? emoji.keywords : []),
              render_comment: '1',
            },
          });
        },
      });

      mount.innerHTML = '';
      mount.appendChild(picker);
    };

    document.body.addEventListener('click', function (event) {
      const toggle = event.target.closest('[data-reactions-toggle]');
      if (!toggle) {
        return;
      }

      const root = toggle.closest('[data-reactions-root]');
      if (!root || root.dataset.canReact !== '1') {
        return;
      }

      event.preventDefault();
      const isSameToggle = activeToggle === toggle;

      if (isPopoverOpen && isSameToggle) {
        toggle.setAttribute('aria-expanded', 'false');
        activeRoot = null;
        activeToggle = null;
        popover.hidePopover();
        return;
      }

      ensurePicker();
      activeRoot = root;
      activeToggle = toggle;
      popover.style.positionAnchor = toggle.style.anchorName;

      if (isPopoverOpen) {
        popover.hidePopover();
      }

      requestAnimationFrame(function () {
        toggle.setAttribute('aria-expanded', 'true');
        popover.showPopover();
      });
    });

    popover.addEventListener('toggle', function (event) {
      isPopoverOpen = event.newState === 'open';
      if (activeToggle) {
        activeToggle.setAttribute('aria-expanded', isPopoverOpen ? 'true' : 'false');
      }
      if (!isPopoverOpen) {
        activeToggle = null;
      }
    });
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initCommentsReactions, { once: true });
  } else {
    initCommentsReactions();
  }
})();
