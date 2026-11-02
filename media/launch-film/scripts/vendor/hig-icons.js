// HIG Native interface icons — original 24×24 line glyphs drawn for this system.
// They stand in for SF Symbols on the web (SF Symbols may not be redistributed). Each key is the
// SF Symbol name to use in a native build, so a web mock and a native app name the same concept.
// Shape data only: [tag, attributes]. Strokes inherit currentColor at 1.8 width, round caps and joins;
// entries marked fill:1 are solid shapes; sw multiplies the stroke width for that shape.
// RTL_FLIP lists glyphs that show reading direction or forward/backward motion: the HIG mirrors them in
// right-to-left layouts (never logos, checkmarks or real-world objects).

function gear() {
  const teeth = 8, ro = 9.6, ri = 7.6, cx = 12, cy = 12;
  let d = '';
  for (let i = 0; i < teeth; i++) {
    const a0 = (i / teeth) * Math.PI * 2, step = (Math.PI * 2) / teeth;
    const pts = [
      [ri, a0 - step * 0.30], [ro, a0 - step * 0.17], [ro, a0 + step * 0.17], [ri, a0 + step * 0.30],
    ];
    for (const [r, a] of pts) {
      const x = (cx + r * Math.cos(a)).toFixed(2), y = (cy + r * Math.sin(a)).toFixed(2);
      d += (d ? 'L' : 'M') + x + ' ' + y;
    }
    const a2 = a0 + step * 0.70;
    d += `A${ri} ${ri} 0 0 1 ${(cx + ri * Math.cos(a2)).toFixed(2)} ${(cy + ri * Math.sin(a2)).toFixed(2)}`;
  }
  return d + 'Z';
}

export const ICONS = {
  'plus': [['path', { d: 'M12 5v14M5 12h14' }]],
  'minus': [['path', { d: 'M5 12h14' }]],
  'xmark': [['path', { d: 'M6.5 6.5l11 11M17.5 6.5l-11 11' }]],
  'checkmark': [['path', { d: 'M5 12.5l4.5 4.5L19 7' }]],
  'chevron.right': [['path', { d: 'M9.5 5.5L16 12l-6.5 6.5' }]],
  'chevron.left': [['path', { d: 'M14.5 5.5L8 12l6.5 6.5' }]],
  'chevron.down': [['path', { d: 'M5.5 9.5L12 16l6.5-6.5' }]],
  'chevron.up': [['path', { d: 'M5.5 14.5L12 8l6.5 6.5' }]],
  'chevron.up.chevron.down': [['path', { d: 'M8 9.5l4-4 4 4M8 14.5l4 4 4-4' }]],
  'magnifyingglass': [['circle', { cx: 10.5, cy: 10.5, r: 6.5 }], ['path', { d: 'M15.4 15.4L20 20' }]],
  'ellipsis': [['circle', { cx: 5.5, cy: 12, r: 1.7, fill: 1 }], ['circle', { cx: 12, cy: 12, r: 1.7, fill: 1 }], ['circle', { cx: 18.5, cy: 12, r: 1.7, fill: 1 }]],
  'ellipsis.circle': [['circle', { cx: 12, cy: 12, r: 9 }], ['circle', { cx: 8, cy: 12, r: 1.2, fill: 1 }], ['circle', { cx: 12, cy: 12, r: 1.2, fill: 1 }], ['circle', { cx: 16, cy: 12, r: 1.2, fill: 1 }]],
  'square.and.arrow.up': [['path', { d: 'M12 3.5V15M8 7.5l4-4 4 4' }], ['path', { d: 'M8.5 10.5H7a2 2 0 0 0-2 2V19a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-6.5a2 2 0 0 0-2-2h-1.5' }]],
  'trash': [['path', { d: 'M4 7h16M9.5 7V4.5h5V7M6.5 7l.9 12.2A2 2 0 0 0 9.4 21h5.2a2 2 0 0 0 2-1.8L17.5 7M10.25 11v6M13.75 11v6' }]],
  'folder': [['path', { d: 'M3.5 7.5A2 2 0 0 1 5.5 5.5h3.6l2 2h7.4a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z' }]],
  'doc': [['path', { d: 'M6 4.5A1.5 1.5 0 0 1 7.5 3H14l4 4v12.5a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 6 19.5z' }], ['path', { d: 'M14 3v4h4' }]],
  'document.on.document': [['path', { d: 'M9 6.5V4.5A1.5 1.5 0 0 1 10.5 3h6L20 6.5v9a1.5 1.5 0 0 1-1.5 1.5H16' }], ['path', { d: 'M4 9.5A1.5 1.5 0 0 1 5.5 8h6.5l3.5 3.5v8a1.5 1.5 0 0 1-1.5 1.5H5.5A1.5 1.5 0 0 1 4 19.5z' }]],
  'document.on.clipboard': [['path', { d: 'M9 4.5H6.5A1.5 1.5 0 0 0 5 6v13.5A1.5 1.5 0 0 0 6.5 21H9M15 4.5h2.5A1.5 1.5 0 0 1 19 6v3' }], ['path', { d: 'M9 3h6v3H9z' }], ['path', { d: 'M11 11.5h6l3 3V21h-9z' }]],
  'scissors': [['circle', { cx: 6.5, cy: 17.5, r: 2.5 }], ['circle', { cx: 17.5, cy: 17.5, r: 2.5 }], ['path', { d: 'M8.3 15.7L18.5 3.5M15.7 15.7L5.5 3.5' }]],
  'pencil': [['path', { d: 'M4.5 19.5l1-4.2L16 4.8a2 2 0 0 1 2.8 0l.4.4a2 2 0 0 1 0 2.8L8.7 18.5z' }], ['path', { d: 'M14.5 6.5l3 3' }]],
  'square.and.pencil': [['path', { d: 'M11 4.5H6A1.5 1.5 0 0 0 4.5 6v12A1.5 1.5 0 0 0 6 19.5h12a1.5 1.5 0 0 0 1.5-1.5v-5' }], ['path', { d: 'M9.5 14.5l.6-3L17.6 4a1.6 1.6 0 0 1 2.3 2.3L12.5 13.9z' }]],
  'paperclip': [['path', { d: 'M18.5 11.5l-7 7a4.5 4.5 0 0 1-6.4-6.4l7.9-7.9a3 3 0 0 1 4.3 4.3l-7.6 7.6a1.5 1.5 0 0 1-2.1-2.1L14.5 7' }]],
  'star': [['path', { d: 'M12 3.8l2.5 5.2 5.7.8-4.1 4 1 5.7L12 16.8l-5.1 2.7 1-5.7-4.1-4 5.7-.8z' }]],
  'star.fill': [['path', { d: 'M12 3.8l2.5 5.2 5.7.8-4.1 4 1 5.7L12 16.8l-5.1 2.7 1-5.7-4.1-4 5.7-.8z', fill: 1 }]],
  'heart': [['path', { d: 'M12 19.5s-7.5-4.6-7.5-10.2A4.1 4.1 0 0 1 12 7a4.1 4.1 0 0 1 7.5 2.3c0 5.6-7.5 10.2-7.5 10.2z' }]],
  'heart.fill': [['path', { d: 'M12 19.5s-7.5-4.6-7.5-10.2A4.1 4.1 0 0 1 12 7a4.1 4.1 0 0 1 7.5 2.3c0 5.6-7.5 10.2-7.5 10.2z', fill: 1 }]],
  'person.crop.circle': [['circle', { cx: 12, cy: 12, r: 9 }], ['circle', { cx: 12, cy: 10, r: 3.2 }], ['path', { d: 'M6.3 18.2a6.6 6.6 0 0 1 11.4 0' }]],
  'bell': [['path', { d: 'M6 16.5V11a6 6 0 0 1 12 0v5.5l1.5 2h-15z' }], ['path', { d: 'M10 20.5a2.2 2.2 0 0 0 4 0' }]],
  'house': [['path', { d: 'M3.5 11.5L12 4l8.5 7.5' }], ['path', { d: 'M6 9.5V20h4.5v-5h3v5H18V9.5' }]],
  'photo': [['rect', { x: 3, y: 5, width: 18, height: 14, rx: 2.5 }], ['circle', { cx: 8.5, cy: 10, r: 1.6 }], ['path', { d: 'M3.5 17l5-4.5 4 3.5 3-2.5 5 4' }]],
  'play.fill': [['path', { d: 'M8 5.2v13.6a.8.8 0 0 0 1.2.7l10.6-6.8a.8.8 0 0 0 0-1.4L9.2 4.5A.8.8 0 0 0 8 5.2z', fill: 1 }]],
  'pause.fill': [['rect', { x: 6.5, y: 5, width: 4, height: 14, rx: 1, fill: 1 }], ['rect', { x: 13.5, y: 5, width: 4, height: 14, rx: 1, fill: 1 }]],
  'mic': [['rect', { x: 9, y: 3, width: 6, height: 11, rx: 3 }], ['path', { d: 'M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21' }]],
  'info.circle': [['circle', { cx: 12, cy: 12, r: 9 }], ['path', { d: 'M12 11v5.5' }], ['circle', { cx: 12, cy: 7.8, r: 1.1, fill: 1 }]],
  'exclamationmark.triangle': [['path', { d: 'M10.3 4.6a2 2 0 0 1 3.4 0l7.2 12.6a2 2 0 0 1-1.7 3H4.8a2 2 0 0 1-1.7-3z' }], ['path', { d: 'M12 9.5v4' }], ['circle', { cx: 12, cy: 16.8, r: 1.1, fill: 1 }]],
  'questionmark': [['path', { d: 'M8.8 8.6a3.3 3.3 0 1 1 4.6 3c-.9.4-1.4 1.1-1.4 2v.9' }], ['circle', { cx: 12, cy: 18.3, r: 1.2, fill: 1 }]],
  'questionmark.circle': [['circle', { cx: 12, cy: 12, r: 9 }], ['path', { d: 'M9.6 9.5a2.5 2.5 0 1 1 3.5 2.3c-.7.3-1.1.8-1.1 1.5v.5' }], ['circle', { cx: 12, cy: 16.6, r: 1, fill: 1 }]],
  'lock': [['rect', { x: 5, y: 10.5, width: 14, height: 10, rx: 2 }], ['path', { d: 'M8 10.5V8a4 4 0 0 1 8 0v2.5' }]],
  'globe': [['circle', { cx: 12, cy: 12, r: 9 }], ['ellipse', { cx: 12, cy: 12, rx: 3.8, ry: 9 }], ['path', { d: 'M3 12h18M4.5 7.5h15M4.5 16.5h15' }]],
  'calendar': [['rect', { x: 4, y: 5, width: 16, height: 15, rx: 2.5 }], ['path', { d: 'M4 10h16M8.5 3v4M15.5 3v4' }]],
  'clock': [['circle', { cx: 12, cy: 12, r: 9 }], ['path', { d: 'M12 7v5l3.5 2' }]],
  'sidebar.left': [['rect', { x: 3, y: 5, width: 18, height: 14, rx: 2.5 }], ['path', { d: 'M9.5 5v14M5.5 8.5h1.5M5.5 11h1.5' }]],
  'line.3.horizontal': [['path', { d: 'M4.5 7h15M4.5 12h15M4.5 17h15' }]],
  'line.3.horizontal.decrease': [['path', { d: 'M4.5 7h15M7.5 12h9M10.5 17h3' }]],
  'list.bullet': [['circle', { cx: 5.5, cy: 7, r: 1.2, fill: 1 }], ['circle', { cx: 5.5, cy: 12, r: 1.2, fill: 1 }], ['circle', { cx: 5.5, cy: 17, r: 1.2, fill: 1 }], ['path', { d: 'M9.5 7h10M9.5 12h10M9.5 17h10' }]],
  'square.grid.2x2': [['rect', { x: 4, y: 4, width: 7, height: 7, rx: 1.8 }], ['rect', { x: 13, y: 4, width: 7, height: 7, rx: 1.8 }], ['rect', { x: 4, y: 13, width: 7, height: 7, rx: 1.8 }], ['rect', { x: 13, y: 13, width: 7, height: 7, rx: 1.8 }]],
  'arrow.uturn.backward': [['path', { d: 'M9 14.5L4.5 10 9 5.5' }], ['path', { d: 'M4.5 10H14a5.5 5.5 0 0 1 0 11h-2.5' }]],
  'arrow.uturn.forward': [['path', { d: 'M15 14.5l4.5-4.5L15 5.5' }], ['path', { d: 'M19.5 10H10a5.5 5.5 0 0 0 0 11h2.5' }]],
  'arrow.clockwise': [['path', { d: 'M19 12a7 7 0 1 1-2.05-4.95' }], ['path', { d: 'M17.5 3.5v4h-4' }]],
  'gearshape': [['path', { d: gear() }], ['circle', { cx: 12, cy: 12, r: 3 }]],
  'checkmark.circle': [['circle', { cx: 12, cy: 12, r: 9 }], ['path', { d: 'M8 12.3l2.8 2.8L16.2 9.5' }]],
  'checkmark.circle.fill': [['circle', { cx: 12, cy: 12, r: 9.5, fill: 1 }], ['path', { d: 'M8 12.3l2.8 2.8L16.2 9.5', knock: 1 }]],
  'xmark.circle.fill': [['circle', { cx: 12, cy: 12, r: 9.5, fill: 1 }], ['path', { d: 'M9 9l6 6M15 9l-6 6', knock: 1 }]],
  'plus.circle': [['circle', { cx: 12, cy: 12, r: 9 }], ['path', { d: 'M12 8v8M8 12h8' }]],
  'circle': [['circle', { cx: 12, cy: 12, r: 9 }]],
  'music.note': [['path', { d: 'M9.5 17.5V5.5l9-2v12' }], ['circle', { cx: 7, cy: 17.5, r: 2.5 }], ['circle', { cx: 16, cy: 15.5, r: 2.5 }]],
  'printer': [['path', { d: 'M7 9V4h10v5M7 17H5.5A1.5 1.5 0 0 1 4 15.5v-5A1.5 1.5 0 0 1 5.5 9h13a1.5 1.5 0 0 1 1.5 1.5v5a1.5 1.5 0 0 1-1.5 1.5H17' }], ['path', { d: 'M7 13.5h10V20H7z' }]],
  'archivebox': [['path', { d: 'M3.5 5h17v4h-17zM5 9v9.5A1.5 1.5 0 0 0 6.5 20h11a1.5 1.5 0 0 0 1.5-1.5V9M10 13h4' }]],
  'tray': [['path', { d: 'M3.5 13.5l2.6-7.2A2 2 0 0 1 8 5h8a2 2 0 0 1 1.9 1.3l2.6 7.2V18a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z' }], ['path', { d: 'M3.5 13.5H8l1.5 2.5h5l1.5-2.5h4.5' }]],
  'paperplane': [['path', { d: 'M20.5 3.5L3.5 10.3l6.8 3.4 3.4 6.8z' }], ['path', { d: 'M10.3 13.7l4.7-4.7' }]],
  'bookmark': [['path', { d: 'M6.5 4.5A1.5 1.5 0 0 1 8 3h8a1.5 1.5 0 0 1 1.5 1.5V21L12 17l-5.5 4z' }]],
  'flag': [['path', { d: 'M5.5 21V4M5.5 4.5c4.5-2 8 2 13 0v9c-5 2-8.5-2-13 0' }]],
  'tag': [['path', { d: 'M3.5 12.6V4.5a1 1 0 0 1 1-1h8.1l8 8a1.4 1.4 0 0 1 0 2l-7 7a1.4 1.4 0 0 1-2 0z' }], ['circle', { cx: 8, cy: 8, r: 1.4, fill: 1 }]],
  'eye': [['path', { d: 'M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z' }], ['circle', { cx: 12, cy: 12, r: 3 }]],
  'location': [['path', { d: 'M20.5 3.5L3.5 11l7.5 2 2 7.5z' }]],
  'wifi': [['path', { d: 'M3 9.5a13 13 0 0 1 18 0M6 12.8a8.6 8.6 0 0 1 12 0M9 16a4.2 4.2 0 0 1 6 0' }], ['circle', { cx: 12, cy: 19, r: 1.2, fill: 1 }]],
  'square.and.arrow.down': [['path', { d: 'M12 3.5V14M8 10l4 4 4-4' }], ['path', { d: 'M5 14.5V19a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-4.5' }]],
  'alarm': [['circle', { cx: 12, cy: 13, r: 7.5 }], ['path', { d: 'M12 9.5V13l2.5 1.5M4.5 6l3-2.5M19.5 6l-3-2.5M7.2 19l-1.7 2M16.8 19l1.7 2' }]],
  'bold': [['path', { d: 'M7.5 4.5h5a3.5 3.5 0 0 1 0 7h-5zM7.5 11.5h6a4 4 0 0 1 0 8h-6z', sw: 1.45 }]],
  'italic': [['path', { d: 'M10.5 4.5h7M6.5 19.5h7M14 4.5l-4 15' }]],
  'underline': [['path', { d: 'M7.5 4.5V11a4.5 4.5 0 0 0 9 0V4.5M6 20.5h12' }]],
  'textformat.superscript': [['path', { d: 'M3.5 19.5L8.5 6.5l5 13M5.4 15.2h6.2' }], ['path', { d: 'M16.6 5.6L18.6 4v7M16.6 11h4' }]],
  'textformat.subscript': [['path', { d: 'M3.5 17.5L8.5 4.5l5 13M5.4 13.2h6.2' }], ['path', { d: 'M16.6 14.6l2-1.6v7M16.6 20h4' }]],
  'text.alignleft': [['path', { d: 'M4 6h16M4 10h10M4 14h16M4 18h10' }]],
  'text.aligncenter': [['path', { d: 'M4 6h16M7 10h10M4 14h16M7 18h10' }]],
  'text.alignright': [['path', { d: 'M4 6h16M10 10h10M4 14h16M10 18h10' }]],
  'text.justify': [['path', { d: 'M4 6h16M4 10h16M4 14h16M4 18h16' }]],
  'plus.square.on.square': [['path', { d: 'M8.5 6V5A1.5 1.5 0 0 1 10 3.5h8.5A1.5 1.5 0 0 1 20 5v8.5a1.5 1.5 0 0 1-1.5 1.5h-1' }], ['rect', { x: 4, y: 8, width: 12, height: 12, rx: 2 }], ['path', { d: 'M10 11v6M7 14h6' }]],
  'text.page.badge.magnifyingglass': [['path', { d: 'M10 21H7.5A1.5 1.5 0 0 1 6 19.5v-15A1.5 1.5 0 0 1 7.5 3H14l4 4v3.5M14 3v4h4M9 9h4M9 12.5h2.5' }], ['circle', { cx: 15.5, cy: 16, r: 3 }], ['path', { d: 'M17.7 18.2L20 20.5' }]],
  'square.3.layers.3d.top.filled': [['path', { d: 'M12 3l8 4-8 4-8-4z', fill: 1 }], ['path', { d: 'M4 12l8 4 8-4M4 17l8 4 8-4' }]],
  'square.3.layers.3d.bottom.filled': [['path', { d: 'M12 3l8 4-8 4-8-4zM4 12l8 4 8-4' }], ['path', { d: 'M4 16.2l8 4 8-4v1.8l-8 4-8-4z', fill: 1 }]],
  'square.2.layers.3d.top.filled': [['path', { d: 'M12 5l8 4-8 4-8-4z', fill: 1 }], ['path', { d: 'M4 15l8 4 8-4' }]],
  'square.2.layers.3d.bottom.filled': [['path', { d: 'M12 5l8 4-8 4-8-4z' }], ['path', { d: 'M4 14.2l8 4 8-4V16l-8 4-8-4z', fill: 1 }]],
  'hand.thumbsup': [['path', { d: 'M4.5 11H7v9H4.5zM7 11l3.4-6.3a1.8 1.8 0 0 1 3.3 1.3L13 10h5.3a1.8 1.8 0 0 1 1.7 2.3l-1.9 6.2A2 2 0 0 1 16.2 20H7' }]],
  'hand.thumbsdown': [['path', { d: 'M4.5 11H7v9H4.5zM7 11l3.4-6.3a1.8 1.8 0 0 1 3.3 1.3L13 10h5.3a1.8 1.8 0 0 1 1.7 2.3l-1.9 6.2A2 2 0 0 1 16.2 20H7', transform: 'matrix(1 0 0 -1 0 24)' }]],
};

export const ICON_NAMES = Object.keys(ICONS);
export const RTL_FLIP = new Set(['chevron.left', 'chevron.right', 'arrow.uturn.backward', 'arrow.uturn.forward', 'list.bullet', 'text.alignleft', 'text.alignright', 'paperplane', 'square.and.pencil']);
