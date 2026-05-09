// ─────────────────────────────────────────────────────────────────────────────
//  EduManage Pro — Layout System v5.1  (loads after api.js)
//  NOTE: Loader, Toast already declared in api.js — not redeclared here
// ─────────────────────────────────────────────────────────────────────────────

var NAV_GROUPS = [
  {
    label: 'Main',
    items: [
      { icon: 'grid',       label: 'Dashboard',    href: '/dashboard',    module: 'dashboard',    color: '#6366f1' },
      { icon: 'home',       label: 'Institution',  href: '/institution',  module: 'institution',  color: '#0ea5e9' },
    ]
  },
  {
    label: 'People',
    items: [
      { icon: 'users',      label: 'Students',      href: '/students',      module: 'students',      color: '#10b981' },
      { icon: 'user-tie',   label: 'Staff & HR',    href: '/staff',         module: 'staff',         color: '#f59e0b' },
      { icon: 'graduation', label: 'Admissions',    href: 'https://rsmemorialpublicschool.com/admission-enquiry/',    module: 'admissions',    color: '#f97316' },
    ]
  },
  {
    label: 'Academics',
    items: [
      { icon: 'book-open',   label: 'Academics',    href: '/academics',    module: 'academics',    color: '#8b5cf6' },
      { icon: 'exam',        label: 'Examinations', href: '/exams',        module: 'exams',        color: '#ef4444' },
      { icon: 'calendar',    label: 'Attendance',   href: '/attendance',   module: 'attendance',   color: '#06b6d4' },
      { icon: 'certificate', label: 'Certificates', href: '/certificates', module: 'certificates', color: '#8b5cf6' },
    ]
  },
  {
    label: 'Finance',
    items: [
      { icon: 'rupee',   label: 'Fees',    href: '/fees',    module: 'fees',    color: '#f97316' },
      { icon: 'payroll', label: 'Payroll', href: '/payroll', module: 'payroll', color: '#10b981' },
    ]
  },
  {
    label: 'Operations',
    items: [
      { icon: 'bus',     label: 'Transport',     href: '/transport',    module: 'transport',    color: '#14b8a6' },
      { icon: 'hostel',  label: 'Hostel',        href: '/hostel',       module: 'hostel',       color: '#d97706' },
      { icon: 'library', label: 'Library',       href: '/library',      module: 'library',      color: '#6366f1' },
      { icon: 'box',     label: 'Inventory',     href: '/inventory',    module: 'inventory',    color: '#84cc16' },
      { icon: 'health',  label: 'Health',        href: '/health',       module: 'health',       color: '#ec4899' },
      { icon: 'chat',    label: 'Communication', href: '/communication',module: 'communication',color: '#a855f7' },
    ]
  },
  {
    label: 'Analytics',
    items: [
      { icon: 'chart', label: 'Reports', href: '/reports', module: 'reports', color: '#0ea5e9' },
    ]
  }
];

var ROLE_MODULE_PRESETS = {
  teacher: ['dashboard', 'students', 'staff', 'academics', 'exams', 'attendance', 'communication'],
  parent: ['dashboard'],
  student: ['dashboard', 'academics', 'exams', 'attendance', 'fees', 'communication'],
  accountant: ['dashboard', 'students', 'fees', 'reports'],
  hr: ['dashboard', 'staff', 'payroll', 'attendance', 'reports'],
};

function isTeacherLikeRole(roleName) {
  roleName = String(roleName || '').trim().toLowerCase();
  return roleName.indexOf('teacher') !== -1 || roleName.indexOf('faculty') !== -1;
}

function filterRestrictedModules(modules, user) {
  if (!Array.isArray(modules)) return modules;
  var roleName = String((user && (user.role_name || user.role)) || '').trim().toLowerCase();
  if (isTeacherLikeRole(roleName)) {
    return modules.filter(function(module) {
      return String(module || '').trim().toLowerCase() !== 'fees';
    });
  }
  return modules;
}

var LAYOUT_ICONS = {
  'grid':        '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  'home':        '<path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/><polyline points="9,22 9,12 15,12 15,22"/>',
  'users':       '<path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75"/>',
  'user-tie':    '<path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/>',
  'graduation':  '<path d="M22 10v6M2 10l10-5 10 5-10 5z"/><path d="M6 12v5c3 3 9 3 12 0v-5"/>',
  'parents':     '<path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87"/><path d="M16 3.13a4 4 0 010 7.75"/>',
  'book-open':   '<path d="M2 3h6a4 4 0 014 4v14a3 3 0 00-3-3H2z"/><path d="M22 3h-6a4 4 0 00-4 4v14a3 3 0 013-3h7z"/>',
  'exam':        '<path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14,2 14,8 20,8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>',
  'calendar':    '<rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>',
  'certificate': '<path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><path d="M9 12h6M9 16h4M14 2v6h6"/>',
  'rupee':       '<line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6"/>',
  'payroll':     '<rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 21V5a2 2 0 00-2-2h-4a2 2 0 00-2 2v16"/>',
  'bus':         '<rect x="1" y="3" width="15" height="13" rx="2"/><polygon points="16,8 20,8 23,11 23,16 16,16 16,8"/><circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="18.5" r="2.5"/>',
  'hostel':      '<path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/><path d="M9 22V12h6v10"/>',
  'library':     '<path d="M4 19.5A2.5 2.5 0 016.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"/>',
  'box':         '<path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 002 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z"/>',
  'health':      '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
  'chat':        '<path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>',
  'chart':       '<line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>',
  'menu':        '<line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/>',
  'logout':      '<path stroke-linecap="round" stroke-linejoin="round" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"/>',
};

function _sbIcon(name, size) {
  size = size || '15px';
  return '<svg style="width:' + size + ';height:' + size + ';flex-shrink:0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">' + (LAYOUT_ICONS[name] || '') + '</svg>';
}

function getAccessibleModules(user) {
  user = user || getUser() || {};
  if (user.is_superadmin) return null;
  var explicitPermissions = Array.isArray(user.permissions) ? user.permissions.filter(function(permission) {
    return permission && permission.can_view;
  }).map(function(permission) {
    return String(permission.module || '').trim().toLowerCase();
  }).filter(Boolean) : [];
  if (explicitPermissions.length) return filterRestrictedModules(explicitPermissions, user);

  var roleName = String(user.role_name || user.role || '').trim().toLowerCase();
  if (!roleName) return null;
  if (roleName.indexOf('super') !== -1 || roleName.indexOf('admin') !== -1 || roleName.indexOf('principal') !== -1) return null;
  if (isTeacherLikeRole(roleName)) return filterRestrictedModules(ROLE_MODULE_PRESETS.teacher, user);
  if (roleName.indexOf('parent') !== -1) return ROLE_MODULE_PRESETS.parent;
  if (roleName.indexOf('student') !== -1) return ROLE_MODULE_PRESETS.student;
  if (roleName.indexOf('account') !== -1 || roleName.indexOf('fee') !== -1) return ROLE_MODULE_PRESETS.accountant;
  if (roleName.indexOf('hr') !== -1 || roleName.indexOf('human resource') !== -1) return ROLE_MODULE_PRESETS.hr;
  return null;
}

function hasModuleAccess(module) {
  var accessibleModules = getAccessibleModules(getUser() || {});
  if (!accessibleModules) return true;
  return accessibleModules.indexOf(String(module || '').toLowerCase()) !== -1;
}

function renderSidebar(activeModule) {
  var user = getUser() || {};
  var nameParts = (user.full_name || 'Admin').split(' ');
  var initials = nameParts.map(w => w[0] || '').join('').substring(0, 2).toUpperCase();
  var accessibleModules = getAccessibleModules(user);

  var navHTML = NAV_GROUPS.map(group => {
    var items = group.items.map(item => {
      if (accessibleModules && accessibleModules.indexOf(String(item.module || '').toLowerCase()) === -1) return '';
      var isActive = activeModule === item.module;

      var iconBg   = isActive ? item.color : '#f3f4f6';
      var iconClr  = isActive ? '#fff' : '#6b7280';
      var iconShadow = isActive ? ('0 3px 10px ' + item.color + '33') : 'none';
      var labelClr = isActive ? '#111827' : '#374151';
      var labelWt  = isActive ? '600' : '500';
      var rowBg    = isActive ? '#eef2ff' : 'transparent';
      var rowBorder= isActive ? '#e0e7ff' : 'transparent';

      return `
      <a href="${
          item.href.startsWith('http') 
            ? item.href 
            : (item.href + window.location.search)
        }"
        target="${
          item.href.startsWith('http') ? '_blank' : '_self'
        }"
        style="display:flex;align-items:center;gap:10px;padding:8px 10px;border-radius:10px;
        text-decoration:none;margin-bottom:4px;transition:all 0.2s;
        background:${rowBg};border:1px solid ${rowBorder}"
        onmouseover="if(this.getAttribute('data-active')!=='1'){this.style.background='#f9fafb';}"
        onmouseout="if(this.getAttribute('data-active')!=='1'){this.style.background='transparent';}"
        data-active="${isActive ? '1' : '0'}">

        <span style="width:32px;height:32px;border-radius:8px;display:flex;align-items:center;
        justify-content:center;background:${iconBg};color:${iconClr};
        box-shadow:${iconShadow}">
          ${_sbIcon(item.icon, '14px')}
        </span>

        <span style="font-size:13px;font-weight:${labelWt};
        color:${labelClr};flex:1">
          ${item.label}
        </span>

        ${isActive ? `<span style="width:5px;height:5px;border-radius:50%;background:${item.color}"></span>` : ''}
      </a>`;
    }).join('');

    if (!items.trim()) return '';

    return `
    <div style="margin-bottom:6px">
      <p style="font-size:10px;font-weight:700;text-transform:uppercase;
      color:#9ca3af;padding:10px 10px 4px">
        ${group.label}
      </p>
      ${items}
    </div>`;
  }).join('');

  return `
  <style>
    #edu-sidebar{
      position:fixed;
      top:0;
      left:0;
      width:260px;
      height:100vh;
      background:#ffffff;
      border-right:1px solid #e5e7eb;
      box-shadow:0 10px 30px rgba(0,0,0,0.05);
      z-index:40;
      display:flex;
      flex-direction:column;
      transition:transform 0.3s ease;
    }

    @media(max-width:1023px){
      #edu-sidebar{transform:translateX(-100%)}
    }

    #edu-sidebar.edu-open{
      transform:translateX(0);
    }

    #edu-sb-overlay{
      display:none;
      position:fixed;
      inset:0;
      background:rgba(0,0,0,0.3);
      z-index:39;
    }

    #edu-sb-overlay.show{display:block}

    .edu-sb-inner{
      flex:1;
      overflow-y:auto;
      padding:10px;
    }
  </style>

  <div id="edu-sb-overlay" onclick="toggleSidebar()"></div>

  <aside id="edu-sidebar">


<!-- LOGO -->
<div style="padding:16px;border-bottom:1px solid #f1f5f9;
display:flex;align-items:center;gap:10px">

  <div style="width:36px;height:36px;border-radius:10px;
  
  display:flex;align-items:center;justify-content:center;font-weight:700">
      <img src="/public/rs.jpeg" style="width:100%;height:100%;object-fit:cover; border-radius:8px"/>
  </div>

  <div>
    <div style="font-weight:800;font-size:14px;color:#111827">
      R S Memorial Public School
    </div>
    <div style="font-size:10px;color:#9ca3af">
      Learn Today for a Better Tomorrow
    </div>
  </div>

</div>

    <!-- MENU -->
    <div class="edu-sb-inner">
      ${navHTML}
    </div>

    <!-- USER -->
    <div style="padding:10px;border-top:1px solid #f1f5f9">

      <div style="display:flex;align-items:center;gap:10px;
      padding:10px;border-radius:10px;background:#f9fafb;
      border:1px solid #e5e7eb">

        <div style="width:34px;height:34px;border-radius:8px;
        background:#6366f1;color:#fff;
        display:flex;align-items:center;justify-content:center;
        font-weight:700">
          ${initials}
        </div>

        <div style="flex:1">
          <div style="font-size:13px;font-weight:600;color:#111827">
            ${user.full_name || 'Admin'}
          </div>
          <div style="font-size:11px;color:#9ca3af">
            ${user.role_name || 'Administrator'}
          </div>
        </div>

        <button onclick="logout()"
        style="width:28px;height:28px;border-radius:7px;
        border:none;background:none;cursor:pointer;color:#6b7280"
        onmouseover="this.style.color='#ef4444'"
        onmouseout="this.style.color='#6b7280'">
          ${_sbIcon('logout', '14px')}
        </button>

      </div>

    </div>

  </aside>
  `;
}
function renderTopbar(title, subtitle) {
  var reportsButton = hasModuleAccess('reports')
    ? '<a href="/reports" ' +
      'style="display:flex;align-items:center;gap:5px;padding:7px 13px;border-radius:8px;' +
      'background:#f5f3ff;border:1px solid #e0e7ff;color:#6366f1;font-size:12px;font-weight:600;' +
      'text-decoration:none;transition:all 0.15s;white-space:nowrap" ' +
      'onmouseover="this.style.background=\'#ede9fe\'" onmouseout="this.style.background=\'#f5f3ff\'">' +
        _sbIcon('chart', '13px') + ' Reports' +
      '</a>'
    : '';
  return '<style>' +
    '.edu-topbar{position:sticky;top:0;z-index:30;' +
    'background:rgba(248,250,252,0.96);' +
    'backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);' +
    'border-bottom:1px solid #e8edf3}' +
    '.edu-tb-inner{display:flex;align-items:center;gap:12px;padding:13px 22px}' +
    '.edu-menu-btn{display:none;width:34px;height:34px;border-radius:8px;background:none;' +
    'border:1px solid #e2e8f0;cursor:pointer;align-items:center;justify-content:center;' +
    'color:#64748b;flex-shrink:0}' +
    '@media(max-width:1023px){.edu-menu-btn{display:flex}}' +
    '.edu-tb-clock{display:flex;align-items:center;gap:6px;padding:6px 11px;border-radius:8px;' +
    'background:#f1f5f9;border:1px solid #e2e8f0;font-size:11.5px;font-weight:500;color:#64748b;white-space:nowrap}' +
    '@media(max-width:640px){.edu-tb-clock{display:none!important}}' +
  '</style>' +
  '<header class="edu-topbar">' +
    '<div class="edu-tb-inner">' +
      '<button class="edu-menu-btn" onclick="toggleSidebar()">' + _sbIcon('menu', '17px') + '</button>' +
      '<div style="flex:1;min-width:0">' +
        '<div style="font-family:\'Outfit\',sans-serif;font-weight:800;font-size:19px;color:#0f172a;line-height:1.2">' + title + '</div>' +
        (subtitle ? '<div style="font-size:12px;color:#94a3b8;margin-top:2px">' + subtitle + '</div>' : '') +
      '</div>' +
      '<div style="display:flex;align-items:center;gap:8px">' +
        '<div class="edu-tb-clock">' +
          '<span style="width:6px;height:6px;border-radius:50%;background:#10b981;flex-shrink:0;display:inline-block"></span>' +
          '<span id="edu-tb-time"></span>' +
        '</div>' +
        reportsButton +
      '</div>' +
    '</div>' +
  '</header>';
}

function toggleSidebar() {
  var sb = document.getElementById('edu-sidebar');
  var ov = document.getElementById('edu-sb-overlay');
  if (!sb) return;
  if (sb.classList.contains('edu-open')) {
    sb.classList.remove('edu-open');
    if (ov) ov.classList.remove('show');
  } else {
    sb.classList.add('edu-open');
    if (ov) ov.classList.add('show');
  }
}

function logout() {
  if (confirm('Do you want to Logout')) {
    Auth.clearAuth();
    window.location.href = '/login';
  }
}

setInterval(function() {
  var el = document.getElementById('edu-tb-time');
  if (el) el.textContent = new Date().toLocaleString('en-IN', { weekday: 'short', day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
}, 1000);

// ─── UI helpers (override api.js versions with improved styling) ──────────────

function statCard(title, value, icon, color, change) {
  var palette = {
    blue:    { bg: '#eff6ff', border: '#bfdbfe', icon: '#3b82f6' },
    green:   { bg: '#f0fdf4', border: '#bbf7d0', icon: '#22c55e' },
    emerald: { bg: '#ecfdf5', border: '#a7f3d0', icon: '#10b981' },
    purple:  { bg: '#faf5ff', border: '#e9d5ff', icon: '#a855f7' },
    orange:  { bg: '#fff7ed', border: '#fed7aa', icon: '#f97316' },
    red:     { bg: '#fef2f2', border: '#fecaca', icon: '#ef4444' },
    indigo:  { bg: '#eef2ff', border: '#c7d2fe', icon: '#6366f1' },
    yellow:  { bg: '#fefce8', border: '#fef08a', icon: '#eab308' },
    teal:    { bg: '#f0fdfa', border: '#99f6e4', icon: '#14b8a6' },
    gray:    { bg: '#f9fafb', border: '#e5e7eb', icon: '#6b7280' },
  };
  var c = palette[color] || palette.blue;
  return '<div style="background:#fff;border-radius:14px;padding:18px;border:1.5px solid ' + c.border + ';transition:all 0.2s;cursor:default" ' +
    'onmouseover="this.style.boxShadow=\'0 8px 24px rgba(0,0,0,0.07)\';this.style.transform=\'translateY(-2px)\'" ' +
    'onmouseout="this.style.boxShadow=\'none\';this.style.transform=\'none\'">' +
    '<div style="display:flex;align-items:flex-start;justify-content:space-between">' +
      '<div>' +
        '<p style="font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;color:' + c.icon + ';font-family:\'DM Sans\',sans-serif">' + title + '</p>' +
        '<p style="font-family:\'Outfit\',sans-serif;font-size:1.875rem;font-weight:800;color:#0f172a;margin-top:5px;line-height:1">' + value + '</p>' +
        (change != null ? '<p style="font-size:11px;margin-top:6px;font-weight:600;color:' + (change >= 0 ? '#16a34a' : '#dc2626') + '">' + (change >= 0 ? '▲' : '▼') + ' ' + Math.abs(change) + '% this month</p>' : '') +
      '</div>' +
      '<div style="width:42px;height:42px;border-radius:11px;display:flex;align-items:center;justify-content:center;background:' + c.bg + ';flex-shrink:0">' +
        '<span style="font-size:1.25rem">' + icon + '</span>' +
      '</div>' +
    '</div>' +
  '</div>';
}

function buildTable(headers, rows, emptyMsg) {
  emptyMsg = emptyMsg || 'No records found';
  return '<div style="overflow-x:auto;border-radius:12px;border:1.5px solid #f1f5f9">' +
    '<table style="width:100%;font-size:13px;border-collapse:collapse">' +
      '<thead><tr style="background:linear-gradient(135deg,#f8fafc,#f1f5f9);border-bottom:2px solid #e2e8f0">' +
        headers.map(function(h) { return '<th style="text-align:left;padding:11px 15px;font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;color:#64748b;white-space:nowrap">' + h + '</th>'; }).join('') +
      '</tr></thead>' +
      '<tbody style="background:#fff">' +
        (rows.length === 0
          ? '<tr><td colspan="' + headers.length + '" style="padding:56px;text-align:center">' +
            '<div style="display:flex;flex-direction:column;align-items:center;gap:10px">' +
              '<div style="width:52px;height:52px;border-radius:14px;background:#f8fafc;display:flex;align-items:center;justify-content:center;font-size:1.5rem">🔍</div>' +
              '<div><p style="font-weight:600;color:#374151">' + emptyMsg + '</p>' +
              '<p style="font-size:12px;color:#94a3b8;margin-top:3px">Try adjusting filters or add new records</p></div>' +
            '</div></td></tr>'
          : rows.map(function(r) {
              return '<tr style="border-top:1px solid #f8fafc;transition:background 0.1s" ' +
                'onmouseover="this.style.background=\'#fafaff\'" onmouseout="this.style.background=\'\'">' + r + '</tr>';
            }).join('')
        ) +
      '</tbody>' +
    '</table>' +
  '</div>';
}

function tdBadge(text, color) {
  color = color || 'gray';
  if (!text && text !== 0) return '<span style="color:#94a3b8;font-size:12px">—</span>';
  var styles = {
    green:  'background:#f0fdf4;color:#16a34a;border:1px solid #bbf7d0',
    red:    'background:#fef2f2;color:#dc2626;border:1px solid #fecaca',
    blue:   'background:#eff6ff;color:#2563eb;border:1px solid #bfdbfe',
    yellow: 'background:#fefce8;color:#ca8a04;border:1px solid #fef08a',
    orange: 'background:#fff7ed;color:#ea580c;border:1px solid #fed7aa',
    purple: 'background:#faf5ff;color:#9333ea;border:1px solid #e9d5ff',
    gray:   'background:#f9fafb;color:#4b5563;border:1px solid #e5e7eb',
    pink:   'background:#fdf2f8;color:#db2777;border:1px solid #fbcfe8',
    teal:   'background:#f0fdfa;color:#0d9488;border:1px solid #99f6e4',
    indigo: 'background:#eef2ff;color:#4338ca;border:1px solid #c7d2fe',
  };
  return '<span style="display:inline-flex;align-items:center;padding:3px 10px;border-radius:999px;font-size:11.5px;font-weight:600;' + (styles[color] || styles.gray) + '">' + text + '</span>';
}

function openModal(id)  { var el = document.getElementById(id); if (el) el.classList.remove('hidden'); }
function closeModal(id) { var el = document.getElementById(id); if (el) el.classList.add('hidden'); }

function inputField(id, label, type, placeholder, required, value) {
  type = type || 'text'; value = value || '';
  return '<div>' +
    '<label style="display:block;font-size:12.5px;font-weight:600;color:#374151;margin-bottom:5px">' + label +
      (required ? '<span style="color:#ef4444;margin-left:2px">*</span>' : '') +
    '</label>' +
    '<input type="' + type + '" id="' + id + '" placeholder="' + (placeholder || '') + '" ' +
    (required ? 'required' : '') + ' value="' + value + '" ' +
    'style="width:100%;padding:9px 13px;border-radius:9px;border:1.5px solid #e2e8f0;background:#f8fafc;' +
    'font-size:13px;outline:none;transition:all 0.15s;font-family:\'DM Sans\',sans-serif;color:#1e293b" ' +
    'onfocus="this.style.background=\'#fff\';this.style.borderColor=\'#6366f1\';this.style.boxShadow=\'0 0 0 3px rgba(99,102,241,0.1)\'" ' +
    'onblur="this.style.background=\'#f8fafc\';this.style.borderColor=\'#e2e8f0\';this.style.boxShadow=\'none\'"/>' +
  '</div>';
}

function selectField(id, label, options, required) {
  return '<div>' +
    '<label style="display:block;font-size:12.5px;font-weight:600;color:#374151;margin-bottom:5px">' + label +
      (required ? '<span style="color:#ef4444;margin-left:2px">*</span>' : '') +
    '</label>' +
    '<select id="' + id + '" ' + (required ? 'required' : '') + ' ' +
    'style="width:100%;padding:9px 13px;border-radius:9px;border:1.5px solid #e2e8f0;background:#f8fafc;' +
    'font-size:13px;outline:none;transition:all 0.15s;font-family:\'DM Sans\',sans-serif;cursor:pointer;color:#1e293b" ' +
    'onfocus="this.style.borderColor=\'#6366f1\';this.style.background=\'#fff\'" ' +
    'onblur="this.style.background=\'#f8fafc\';this.style.borderColor=\'#e2e8f0\'">' +
    options + '</select>' +
  '</div>';
}
