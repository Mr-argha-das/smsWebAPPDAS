// ─────────────────────────────────────────────────────────────────────────────
//  EduManage Pro — Complete API Client v3.0  (PRODUCTION FIXED)
//  All method names, paths, and aliases verified against backend routes
// ─────────────────────────────────────────────────────────────────────────────

// Auto-detect server URL so it works on any host/port
const API_BASE = window.location.origin + '/api/v1';

// ─── Auth / Token ─────────────────────────────────────────────────────────────
const Auth = {
  getToken:    () => localStorage.getItem('access_token'),
  getUser:     () => { try { return JSON.parse(localStorage.getItem('user') || 'null'); } catch { return null; } },
  setAuth(token, user) {
    localStorage.setItem('access_token', token);
    localStorage.setItem('user', JSON.stringify(user));
    if (user?.assigned_school_id) localStorage.setItem('school_id', user.assigned_school_id);
  },
  clearAuth() { ['access_token','user','school_id','academic_year_id'].forEach(k => localStorage.removeItem(k)); },
  isLoggedIn:  () => !!localStorage.getItem('access_token'),
  getSchoolId: () => localStorage.getItem('school_id'),
  // aliases used by some pages
  setToken(t)  { localStorage.setItem('access_token', t); },
  clearToken() { this.clearAuth(); }
};

// ─── HTTP Client ──────────────────────────────────────────────────────────────
const API = {
  _cache: new Map(),
  _pending: new Map(),
  _cacheTtlMs: 12000,
  clearCache() {
    this._cache.clear();
    this._pending.clear();
  },
  async request(method, endpoint, data = null, params = null) {
    let urlStr;
    if (endpoint.startsWith('http') || endpoint.includes('?')) {
      urlStr = endpoint.startsWith('http') ? endpoint : `${API_BASE}${endpoint}`;
    } else {
      const u = new URL(`${API_BASE}${endpoint}`);
      if (params) {
        Object.entries(params).forEach(([k,v]) => {
          if (v !== null && v !== undefined && v !== '') u.searchParams.append(k, String(v));
        });
      }
      urlStr = u.toString();
    }
    const options = { method, headers: { 'Content-Type': 'application/json' } };
    const token = Auth.getToken();
    if (token) options.headers['Authorization'] = `Bearer ${token}`;
    if (data !== null && data !== undefined) options.body = JSON.stringify(data);
    const isGet = method === 'GET';
    const cacheKey = isGet ? urlStr : '';
    if (isGet) {
      const cached = API._cache.get(cacheKey);
      if (cached && Date.now() - cached.at < API._cacheTtlMs) return cached.value;
      const pending = API._pending.get(cacheKey);
      if (pending) return pending;
    } else {
      API.clearCache();
    }
    try {
      const requestPromise = fetch(urlStr, options).then(async (res) => {
        if (res.status === 401) {
          Auth.clearAuth();
          if (!location.pathname.endsWith('login.html')) location.href = '/login';
          return null;
        }
        const json = await res.json();
        if (!res.ok) {
          let detail = json.detail || json.message || `HTTP ${res.status}`;
          if (Array.isArray(detail)) {
            detail = detail.map(item => item?.msg || JSON.stringify(item)).join(', ');
          } else if (typeof detail === 'object' && detail !== null) {
            detail = JSON.stringify(detail);
          }
          throw new Error(detail);
        }
        if (isGet) API._cache.set(cacheKey, { at: Date.now(), value: json });
        return json;
      });
      if (isGet) API._pending.set(cacheKey, requestPromise);
      return await requestPromise;
    } catch (e) {
      if (e.message === 'Failed to fetch') throw new Error('Unable to connect to the server. Start the backend with: uvicorn main:app --reload');
      throw e;
    } finally {
      if (isGet) API._pending.delete(cacheKey);
    }
  },
  get:    (ep, p) => API.request('GET',    ep, null, p),
  post:   (ep, d) => API.request('POST',   ep, d),
  put:    (ep, d) => API.request('PUT',    ep, d),
  patch:  (ep, d) => API.request('PATCH',  ep, d),
  delete: (ep)    => API.request('DELETE', ep),
  async upload(endpoint, formData) {
    const token = Auth.getToken();
    const res = await fetch(`${API_BASE}${endpoint}`, {
      method: 'POST',
      headers: token ? { 'Authorization': `Bearer ${token}` } : {},
      body: formData
    });
    if (!res.ok) { const j = await res.json(); throw new Error(j.detail || j.message || 'Upload failed'); }
    API.clearCache();
    return res.json();
  }
};
// lowercase alias — all pages use api.get / api.post etc.
const api = API;

// ─── Toast ────────────────────────────────────────────────────────────────────
const Toast = {
  _c: null,
  _getC() {
    if (!this._c) {
      this._c = document.getElementById('toast-container');
      if (!this._c) {
        this._c = document.createElement('div');
        this._c.id = 'toast-container';
        this._c.className = 'fixed top-4 right-4 z-[9999] flex flex-col gap-2 pointer-events-none';
        document.body.appendChild(this._c);
      }
    }
    return this._c;
  },
  show(msg, type = 'success', dur = 3500) {
    const c = this._getC();
    const cfg = { success: ['bg-emerald-500','✓'], error: ['bg-red-500','✗'], warning: ['bg-amber-500','⚠'], info: ['bg-blue-500','ℹ'] };
    const [bg, icon] = cfg[type] || cfg.info;
    const t = document.createElement('div');
    t.className = `pointer-events-auto ${bg} text-white px-5 py-3 rounded-xl shadow-2xl flex items-center gap-3 min-w-[260px] max-w-sm transition-all duration-300 translate-x-full opacity-0`;
    t.innerHTML = `<span class="text-lg font-bold">${icon}</span><span class="text-sm flex-1 font-medium">${msg}</span><button onclick="this.parentElement.remove()" class="text-white/70 hover:text-white ml-2 text-xl leading-none">×</button>`;
    c.appendChild(t);
    requestAnimationFrame(() => requestAnimationFrame(() => t.classList.remove('translate-x-full', 'opacity-0')));
    setTimeout(() => { t.classList.add('translate-x-full', 'opacity-0'); setTimeout(() => t.remove(), 300); }, dur);
  },
  success: (m) => Toast.show(m, 'success'),
  error:   (m) => Toast.show(m, 'error'),
  warning: (m) => Toast.show(m, 'warning'),
  info:    (m) => Toast.show(m, 'info'),
};

// ─── Global Utility Functions ─────────────────────────────────────────────────
function showToast(msg, type = 'success') { Toast.show(msg, type); }
function getUser()    { return Auth.getUser(); }
function requireAuth() { if (!Auth.isLoggedIn()) { location.href = '/login'; return false; } return true; }
function getAssignedBranchCode() { return getUser()?.assigned_branch_code || ''; }
function getAllowedBranchCodes() {
  const user = getUser() || {};
  const assigned = user.assigned_branch_code ? [user.assigned_branch_code] : [];
  const allowed = Array.isArray(user.allowed_branch_codes) ? user.allowed_branch_codes : [];
  return [...new Set([...assigned, ...allowed].filter(Boolean))];
}
function getScopedBranchCode(requestedBranchCode = '') {
  const assignedBranch = getAssignedBranchCode();
  if (assignedBranch) return assignedBranch;
  const allowedBranches = getAllowedBranchCodes();
  if (!allowedBranches.length) return requestedBranchCode || '';
  if (requestedBranchCode && allowedBranches.includes(requestedBranchCode)) return requestedBranchCode;
  return allowedBranches[0];
}
function applyBranchAccessToSelect(selectId, requestedBranchCode = '') {
  const el = document.getElementById(selectId);
  if (!el) return getScopedBranchCode(requestedBranchCode);
  const scopedBranch = getScopedBranchCode(requestedBranchCode);
  const assignedBranch = getAssignedBranchCode();
  const allowedBranches = getAllowedBranchCodes();
  Array.from(el.options).forEach(opt => {
    if (!opt.value) return;
    if (allowedBranches.length && !allowedBranches.includes(opt.value)) opt.remove();
  });
  if (scopedBranch && Array.from(el.options).some(opt => opt.value === scopedBranch)) {
    el.value = scopedBranch;
  }
  el.disabled = !!assignedBranch;
  return scopedBranch;
}
function formatCurrency(n) {
  if (n == null || isNaN(Number(n))) return '₹0';
  return '₹' + Number(n).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
function formatDate(d) {
  if (!d) return '—';
  try { return new Date(d).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }); }
  catch { return '—'; }
}
function debounce(fn, ms = 400) {
  let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

async function initializeSchoolContext(forceRefresh = false) {
  if (!Auth.isLoggedIn()) return null;
  const user = getUser() || {};
  if (user.assigned_school_id) {
    localStorage.setItem('school_id', user.assigned_school_id);
    return user.assigned_school_id;
  }
  const currentSchoolId = localStorage.getItem('school_id');
  try {
    const res = await API.get('/institution/school');
    const schools = res?.data || [];
    if (!schools.length) {
      localStorage.removeItem('school_id');
      return null;
    }
    if (currentSchoolId && !forceRefresh) {
      const validExisting = schools.find(s => s.id === currentSchoolId);
      if (validExisting) return currentSchoolId;
    }
    const validExisting = schools.find(s => s.id === currentSchoolId);
    const selectedId = validExisting?.id || schools[0].id;
    localStorage.setItem('school_id', selectedId);
    return selectedId;
  } catch (e) {
    return currentSchoolId || null;
  }
}

// ─── UI Helpers ───────────────────────────────────────────────────────────────
function statCard(title, value, icon, color, change) {
  const colors = {
    blue:'from-blue-500 to-blue-600', green:'from-emerald-500 to-emerald-600',
    emerald:'from-emerald-500 to-emerald-600', purple:'from-violet-500 to-violet-600',
    orange:'from-orange-500 to-orange-600', red:'from-red-500 to-red-600',
    indigo:'from-indigo-500 to-indigo-600', yellow:'from-amber-500 to-amber-600',
    teal:'from-teal-500 to-teal-600', pink:'from-pink-500 to-pink-600',
    gray:'from-gray-400 to-gray-500'
  };
  const grad = colors[color] || colors.blue;
  return `<div class="bg-white rounded-2xl p-5 shadow-sm border border-gray-100 hover:shadow-md transition-shadow">
    <div class="flex items-center justify-between">
      <div>
        <p class="text-gray-500 text-sm font-medium">${title}</p>
        <p class="text-2xl font-bold text-gray-900 mt-1">${value}</p>
        ${change != null ? `<p class="text-xs mt-1 ${change >= 0 ? 'text-emerald-600' : 'text-red-500'}">${change >= 0 ? '↑' : '↓'}${Math.abs(change)}%</p>` : ''}
      </div>
      <div class="w-12 h-12 bg-gradient-to-br ${grad} rounded-xl flex items-center justify-center text-2xl shadow-md">${icon}</div>
    </div>
  </div>`;
}

function buildTable(headers, rows, emptyMsg = 'No data found') {
  const th = headers.map(h => `<th class="text-left px-4 py-3 text-gray-600 font-semibold text-xs uppercase tracking-wide whitespace-nowrap">${h}</th>`).join('');
  const tb = rows.length === 0
    ? `<tr><td colspan="${headers.length}" class="text-center py-12 text-gray-400"><div class="flex flex-col items-center gap-2"><span class="text-3xl">🔍</span><span>${emptyMsg}</span></div></td></tr>`
    : rows.map(r => `<tr class="hover:bg-gray-50 transition-colors">${r}</tr>`).join('');
  return `<div class="overflow-x-auto rounded-xl border border-gray-200"><table class="w-full text-sm"><thead><tr class="bg-gray-50 border-b border-gray-200">${th}</tr></thead><tbody class="divide-y divide-gray-100">${tb}</tbody></table></div>`;
}

function tdBadge(text, color = 'gray') {
  if (!text && text !== 0) return '<span class="text-gray-400">—</span>';
  const m = {
    green:'bg-emerald-100 text-emerald-700', red:'bg-red-100 text-red-700',
    blue:'bg-blue-100 text-blue-700', yellow:'bg-amber-100 text-amber-700',
    orange:'bg-orange-100 text-orange-700', purple:'bg-violet-100 text-violet-700',
    gray:'bg-gray-100 text-gray-600', pink:'bg-pink-100 text-pink-700',
    teal:'bg-teal-100 text-teal-700', indigo:'bg-indigo-100 text-indigo-700'
  };
  return `<span class="inline-flex items-center px-2.5 py-0.5 rounded-lg text-xs font-semibold ${m[color] || m.gray}">${text}</span>`;
}

const Loader = {
  show(el, text = 'Loading...') {
    if (typeof el === 'string') el = document.getElementById(el);
    if (el) el.innerHTML = `<div class="flex flex-col items-center justify-center py-16 text-gray-400"><div class="w-10 h-10 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mb-3"></div><span class="text-sm">${text}</span></div>`;
  },
  btn(btn, loading = true, text = 'Saving...') {
    if (typeof btn === 'string') btn = document.getElementById(btn);
    if (!btn) return;
    if (loading) { btn._orig = btn.innerHTML; btn.disabled = true; btn.innerHTML = `<span class="inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin mr-2 align-middle"></span>${text}`; }
    else { btn.disabled = false; btn.innerHTML = btn._orig || text; }
  }
};

// ─── ══════════════════════════════════════════════════════════════════════ ───
//  PHASE 1 — CORE APIs  (paths verified against backend routes)
// ─── ══════════════════════════════════════════════════════════════════════ ───

// AUTH  → prefix: /auth
const AuthAPI = {
  login:          (username, password) => API.post('/auth/login', { username, password }),
  register:       (d)     => API.post('/auth/register', d),
  me:             ()      => API.get('/auth/me'),
  changePassword: (old_password, new_password) => API.put('/auth/me/change-password', null, { old_password, new_password }),
  getRoles:       ()      => API.get('/auth/roles'),
  createRole:     (d)     => API.post('/auth/roles', d),
};

// INSTITUTION  → prefix: /institution
const SchoolAPI = {
  create:       (d)   => API.post('/institution/school', d),
  getAll:       ()    => API.get('/institution/school'),
  get:          (id)  => API.get(`/institution/school/${id}`),
  update:       (id,d)=> API.put(`/institution/school/${id}`, d),
  uploadLogo:   (fd)  => API.upload('/institution/upload-logo', fd),
  dashboard:    (id, branchCode)  => API.get(`/institution/dashboard/${id}`, { branch_code: branchCode }),
  createAY:     (d)   => API.post('/institution/academic-year', d),
  listAY:       (sid) => API.get(`/institution/academic-year?school_id=${sid}`),
  updateAY:     (id,d)=> API.put(`/institution/academic-year/${id}`, d),
  deleteAY:     (id)  => API.delete(`/institution/academic-year/${id}`),
  setCurrentAY: (id)  => API.patch(`/institution/academic-year/${id}/set-current`, {}),
  createClass:  (d)   => API.post('/institution/class', d),
  listClasses:  (sid) => API.get(`/institution/class?school_id=${sid}`),
  updateClass:  (id,d)=> API.put(`/institution/class/${id}`, d),
  deleteClass:  (id)  => API.delete(`/institution/class/${id}`),
  listSections: (sid, cid) => API.get(`/institution/section?school_id=${sid}${cid ? '&classroom_id=' + cid : ''}`),
  createSubject:(d)   => API.post('/institution/subject', d),
  listSubjects: (sid, p = {}) => API.get('/institution/subject', { school_id: sid, ...p }),
  getSubjectMapping: (p) => API.get('/institution/subject-mapping', p),
  saveSubjectMapping:(d) => API.post('/institution/subject-mapping', d),
  updateSubject:(id,d)=> API.put(`/institution/subject/${id}`, d),
  deleteSubject:(id)  => API.delete(`/institution/subject/${id}`),
  createGrading:(d)   => API.post('/institution/grading-system', d),
  listGrading:  (sid) => API.get(`/institution/grading-system?school_id=${sid}`),
  updateGrading:(id,d)=> API.put(`/institution/grading-system/${id}`, d),
  deleteGrading:(id)  => API.delete(`/institution/grading-system/${id}`),
};

// STUDENTS  → prefix: /students
const StudentAPI = {
  create:     (d)     => API.post('/students', d),
  list:       (p)     => API.get('/students', p),
  searchSiblings:(p)  => API.get('/students/search-siblings', p),
  get:        (id)    => API.get(`/students/${id}`),
  profile:    (id)    => API.get(`/students/${id}/profile-summary`),
  update:     (id,d)  => API.put(`/students/${id}`, d),
  delete:     (id)    => API.delete(`/students/${id}`),
  uploadPhoto:(id,fd) => API.upload(`/students/${id}/upload-photo`, fd),
  uploadDoc:  (id,fd) => API.upload(`/students/${id}/upload-document`, fd),
  templateUrl:(schoolId = '', academicYearId = '') => {
    const params = new URLSearchParams();
    if (schoolId) params.append('school_id', schoolId);
    if (academicYearId) params.append('academic_year_id', academicYearId);
    return `${API_BASE}/students/import/template${params.toString() ? `?${params.toString()}` : ''}`;
  },
  exportUrl: (params = {}) => {
    const query = new URLSearchParams();
    Object.entries(params || {}).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') query.append(key, value);
    });
    return `${API_BASE}/students/export/csv${query.toString() ? `?${query.toString()}` : ''}`;
  },
  importCsv:  (schoolId, academicYearId, fd, branchCode = '', branchName = '', updateExisting = false) => {
    const params = new URLSearchParams({ school_id: schoolId, academic_year_id: academicYearId });
    if (branchCode) params.append('branch_code', branchCode);
    if (branchName) params.append('branch_name', branchName);
    if (updateExisting) params.append('update_existing', 'true');
    return API.upload(`/students/import/csv?${params.toString()}`, fd);
  },
  promote:    (id,d)  => API.post(`/students/${id}/promote`, d),
  generateTC: (id,d)  => API.post(`/students/${id}/transfer-certificate`, d),
  getTC:      (id)    => API.get(`/students/${id}/transfer-certificate`),
  stats:      (sid, ayid, branchCode)   => API.get('/students/stats/summary', { school_id: sid, academic_year_id: ayid, branch_code: branchCode }),
};

// STAFF  → prefix: /staff
const StaffAPI = {
  create:           (d)     => API.post('/staff', d),
  list:             (p)     => API.get('/staff', p),
  get:              (id)    => API.get(`/staff/${id}`),
  update:           (id,d)  => API.put(`/staff/${id}`, d),
  setActive:        (id,d)  => API.patch(`/staff/${id}/active`, d),
  createAssignment: (d)     => API.post('/staff/assignments', d),
  updateAssignment: (id,d)  => API.put(`/staff/assignments/${id}`, d),
  deleteAssignment: (id)    => API.delete(`/staff/assignments/${id}`),
  getAssignments:   (p)     => API.get('/staff/assignments', p),
  listAssignments:  (p)     => API.get('/staff/assignments', p),
  getMyProfile:     (sid)    => API.get('/staff/me/profile', { school_id: sid }),
  getLeaveTypes:    (sid)    => API.get('/staff/leave/types', { school_id: sid }),
  applyLeave:       (d)     => API.post('/staff/leave/apply', d),
  getLeaves:        (p)     => API.get('/staff/leave/applications', p),
  listLeaves:       (p)     => API.get('/staff/leave/applications', p),
  leaveAction:      (id,d)  => API.patch(`/staff/leave/${id}/action?action=${encodeURIComponent(typeof d === 'string' ? d : (d?.action || ''))}${d?.rejection_reason ? `&rejection_reason=${encodeURIComponent(d.rejection_reason)}` : ''}`, {}),
  actionLeave:      (id,d)  => API.patch(`/staff/leave/${id}/action?action=${encodeURIComponent(typeof d === 'string' ? d : (d?.action || ''))}${d?.rejection_reason ? `&rejection_reason=${encodeURIComponent(d.rejection_reason)}` : ''}`, {}),
  generateSalary:   (d)     => API.post('/staff/salary/generate', d),
  getSalarySlips:   (id)    => API.get(`/staff/${id}/salary-slips`),
  listSalary:       (id)    => API.get(`/staff/${id}/salary-slips`),
};

// ATTENDANCE  → prefix: /attendance
const AttendanceAPI = {
  markStudent:    (d)   => API.post('/attendance/student/mark', d),
  markStudents:   (d)   => API.post('/attendance/student/mark', d),
  getStudent:     (p)   => API.get('/attendance/student', p),
  getStudentAtt:  (p)   => API.get('/attendance/student', p),
  getSummary:     (sid, date) => API.get(`/attendance/summary/${sid}`, { date }),
  markStaff:      (d)   => API.post('/attendance/staff/mark', d),
  markMyStaff:    (d)   => API.post('/attendance/staff/self-checkin', d),
  punchOutMyStaff:(d)   => API.post('/attendance/staff/self-checkout', d),
  getMyStaffAtt:  (p)   => API.get('/attendance/staff/self', p),
  getTeacherClasses:(p) => API.get('/attendance/teacher/classes', p),
  getStaffAtt:    (p)   => API.get('/attendance/staff', p),
  getHolidays:    (sid) => API.get('/attendance/holiday', { school_id: sid }),
  addHoliday:     (d)   => API.post('/attendance/holiday', d),
  report:         (p)   => API.get('/attendance/student/report', p),
};

// FEES  → prefix: /fees
const FeesAPI = {
  createCategory: (d)    => API.post('/fees/category', d),
  getCategories:  (sid)  => API.get(`/fees/category?school_id=${sid}`),
  listCategories: (sid)  => API.get(`/fees/category?school_id=${sid}`),
  createStructure:(d)    => API.post('/fees/structure', d),
  getStructures:  (p)    => API.get('/fees/structure', p),
  listStructures: (p)    => API.get('/fees/structure', p),
  updateStructure:(id,d) => API.put(`/fees/structure/${id}`, d),
  deleteStructure:(id)   => API.delete(`/fees/structure/${id}`),
  createInvoice:  (d)    => API.post('/fees/invoice', d),
  getInvoices:    (p)    => API.get('/fees/invoice', p),
  listInvoices:   (p)    => API.get('/fees/invoice', p),
  getInvoice:     (id)   => API.get(`/fees/invoice/${id}`),
  updateInvoice:  (id,d) => API.put(`/fees/invoice/${id}`, d),
  deleteInvoice:  (id)   => API.delete(`/fees/invoice/${id}`),
  sendInvoiceEmail: (id, d) => API.post(`/fees/invoice/${id}/send-email`, d),
  recordPayment:  (d)    => API.post('/fees/payment', d),
  collectPayment: (d)    => API.post('/fees/payment', d),  // POST /fees/payment
  paymentHistory: (p)    => API.get('/fees/payment/history', p),
  getDues:        (p)    => API.get('/fees/dues', p),
  duesReport:     (p)    => API.get('/fees/dues', p),
  getSummary:     (sid, branchCode)  => API.get('/fees/reports/summary', { school_id: sid, branch_code: branchCode }),
  stats:          (sid, branchCode)  => API.get('/fees/reports/summary', { school_id: sid, branch_code: branchCode }),
};

// EXAMS  → prefix: /exams
const ExamAPI = {
  create:         (d)     => API.post('/exams', d),
  seedDefaults:   (sid,ayid) => API.post(`/exams/seed-defaults?school_id=${sid}&academic_year_id=${ayid}`, {}),
  list:           (p)     => API.get('/exams', p),
  update:         (id,d)  => API.put(`/exams/${id}`, d),
  delete:         (id)    => API.delete(`/exams/${id}`),
  updateStatus:   (id,status)  => API.patch(`/exams/${id}/status?status=${encodeURIComponent(status)}`, {}),
  getRollNumbers: (p)     => API.get('/exams/roll-numbers', p),
  saveRollNumbers:(d)     => API.post('/exams/roll-numbers', d),
  getDateSheet:   (p)     => API.get('/exams/date-sheet', p),
  saveDateSheet:  (d)     => API.post('/exams/date-sheet', d),
  enterMarksBulk: (d)     => API.post('/exams/marks/bulk', d),
  getMarksMatrix: (p)     => API.get('/exams/marks/matrix', p),
  saveMarksMatrix:(d)     => API.post('/exams/marks/matrix', d),
  bulkMarks:      (d)     => API.post('/exams/marks/bulk', d),
  getMarks:       (p)     => API.get('/exams/marks', p),
  generateResults:(id,classId,secId) => API.post(`/exams/${id}/generate-results?classroom_id=${classId}&section_id=${secId}`, {}),
  getResults:     (p)     => API.get('/exams/results', p),
  listResults:    (p)     => API.get('/exams/results', p),
  getResults:     (p)     => API.get('/exams/results', p),
};

// ACADEMICS  → prefix: /academics
const AcademicAPI = {
  createTimetable:  (d)   => API.post('/academics/timetable', d),
  getTimetable:     (schoolIdOrParams, classroomId, sectionId) => {
    if (typeof schoolIdOrParams === 'object' && schoolIdOrParams !== null) {
      return API.get('/academics/timetable', schoolIdOrParams);
    }
    return API.get('/academics/timetable', {
      school_id: schoolIdOrParams,
      classroom_id: classroomId,
      section_id: sectionId
    });
  },
  createHomework:   (d)   => API.post('/academics/homework', d),
  getHomework:      (p)   => API.get('/academics/homework', p),
  listHomework:     (p)   => API.get('/academics/homework', p),
  uploadMaterial:   (d)   => API.post('/academics/study-material', d),
  createMaterial:   (d)   => API.post('/academics/study-material', d),
  getMaterials:     (p)   => API.get('/academics/study-material', p),
  listMaterials:    (p)   => API.get('/academics/study-material', p),
  scheduleOnlineClass:(d) => API.post('/academics/online-class', d),
  createOnlineClass:(d)   => API.post('/academics/online-class', d),
  getOnlineClasses: (p)   => API.get('/academics/online-class', p),
  listOnlineClass:  (p)   => API.get('/academics/online-class', p),
};

// ─── ══════════════════════════════════════════════════════════════════════ ───
//  PHASE 2 — EXTENDED APIs
// ─── ══════════════════════════════════════════════════════════════════════ ───

// TRANSPORT  → prefix: /transport
const TransportAPI = {
  createRoute:      (d)         => API.post('/transport/route', d),
  getRoutes:        (sid, branchCode)       => API.get('/transport/route', { school_id: sid, branch_code: branchCode }),
  updateRoute:      (id,d)      => API.put(`/transport/route/${id}`, d),
  deleteRoute:      (id)        => API.delete(`/transport/route/${id}`),
  createVehicle:    (d)         => API.post('/transport/vehicle', d),
  getVehicles:      (sid)       => API.get(`/transport/vehicle?school_id=${sid}`),
  createDriver:     (d)         => API.post('/transport/driver', d),
  getDrivers:       (sid)       => API.get(`/transport/driver?school_id=${sid}`),
  assignStudent:    (d)         => API.post('/transport/student-transport', d),
  getStudentTransport:(sid,rid,branchCode) => API.get('/transport/student-transport', { school_id: sid, route_id: rid, branch_code: branchCode }),
  addMaintenance:   (d)         => API.post('/transport/maintenance', d),
  getMaintenance:   (vid)       => API.get(`/transport/maintenance/${vid}`),
  getStats:         (sid, branchCode)       => API.get(`/transport/stats/${sid}`, { branch_code: branchCode }),
};

// LIBRARY  → prefix: /library
const LibraryAPI = {
  addBook:        (d)         => API.post('/library/book', d),
  getBooks:       (p)         => API.get('/library/book', p),
  updateBook:     (id,d)      => API.put(`/library/book/${id}`, d),
  deleteBook:     (id)        => API.delete(`/library/book/${id}`),
  addMember:      (d)         => API.post('/library/member', d),
  getMembers:     (sid,type)  => API.get(`/library/member?school_id=${sid}${type ? '&member_type=' + type : ''}`),
  issueBook:      (d)         => API.post('/library/issue', d),
  returnBook:     (id)        => API.patch(`/library/return/${id}`, {}),
  getIssued:      (p)         => API.get('/library/issued', p),
  addCategory:    (d)         => API.post('/library/category', d),
  getCategories:  (sid)       => API.get(`/library/category?school_id=${sid}`),
  getStats:       (sid)       => API.get(`/library/stats/${sid}`),
};

// INVENTORY  → prefix: /inventory
const InventoryAPI = {
  addAsset:             (d)      => API.post('/inventory/asset', d),
  getAssets:            (p)      => API.get('/inventory/asset', p),
  updateAsset:          (id,d)   => API.put(`/inventory/asset/${id}`, d),
  deleteAsset:          (id)     => API.delete(`/inventory/asset/${id}`),
  getAssetCategories:   (sid)    => API.get(`/inventory/asset-category?school_id=${sid}`),
  createAssetCategory:  (d)      => API.post('/inventory/asset-category', d),
  addStockItem:         (d)      => API.post('/inventory/stock-item', d),
  getStockItems:        (sid,low,search,className)=> API.get('/inventory/stock-item', { school_id: sid, low_stock: low ? 'true' : '', search: search || '', class_name: className || '' }),
  updateStockItem:      (id,d)   => API.put(`/inventory/stock-item/${id}`, d),
  deleteStockItem:      (id)     => API.delete(`/inventory/stock-item/${id}`),
  addStockTransaction:  (d)      => API.post('/inventory/stock-transaction', d),
  getStockTransactions: (id)     => API.get(`/inventory/stock-transactions/${id}`),
  getStats:             (sid)    => API.get(`/inventory/stats/${sid}`),
};

// HEALTH  → prefix: /health
const HealthAPI = {
  createRecord:   (d)       => API.post('/health/record', d),
  getRecord:      (id,type) => API.get(`/health/record/${id}?member_type=${type || 'Student'}`),
  addVisit:       (d)       => API.post('/health/medical-visit', d),
  getVisits:      (p)       => API.get('/health/visits', p),
  createAlert:    (d)       => API.post('/health/alert', d),
  getAlerts:      (sid)     => API.get(`/health/alerts/${sid}`),
};

// COMMUNICATION  → prefix: /communication
const CommAPI = {
  createNotice:     (d)       => API.post('/communication/notice', d),
  getNotices:       (p)       => API.get('/communication/notice', p),
  createEvent:      (d)       => API.post('/communication/event', d),
  getEvents:        (sid,up)  => API.get(`/communication/event?school_id=${sid}${up ? '&upcoming_only=true' : ''}`),
  sendMessage:      (d)       => API.post('/communication/message', d),
  getMessages:      (uid,sid) => API.get(`/communication/messages/${uid}?school_id=${sid}`),
  getNotifications: (uid,sid,ur) => API.get(`/communication/notifications/${uid}?school_id=${sid}${ur ? '&unread_only=true' : ''}`),
  markRead:         (id)      => API.patch(`/communication/notifications/${id}/read`, {}),
};

// REPORTS  → prefix: /reports
const ReportsAPI = {
  overview:           (sid,ayid)    => API.get(`/reports/overview/${sid}${ayid ? '?academic_year_id=' + ayid : ''}`),
  attendanceClassWise:(sid,date)    => API.get(`/reports/attendance/class-wise?school_id=${sid}${date ? '&date=' + date : ''}`),
  attendanceMonthly:  (sid,y,m)     => API.get(`/reports/attendance/monthly-trend?school_id=${sid}&year=${y}&month=${m}`),
  feesMonthly:        (sid,y,startDate,endDate) => API.get('/reports/fees/monthly-collection', { school_id: sid, year: y, start_date: startDate, end_date: endDate }),
  feeDefaulters:      (sid,ayid)    => API.get(`/reports/fees/defaulters?school_id=${sid}${ayid ? '&academic_year_id=' + ayid : ''}`),
  studentsClassWise:  (sid,ayid)    => API.get(`/reports/students/class-wise-count?school_id=${sid}${ayid ? '&academic_year_id=' + ayid : ''}`),
  resultAnalysis:     (sid,eid,cid) => API.get(`/reports/exams/result-analysis?school_id=${sid}&exam_id=${eid}${cid ? '&classroom_id=' + cid : ''}`),
  staffAttendance:    (sid,m,y)     => API.get(`/reports/staff/attendance-summary?school_id=${sid}&month=${m}&year=${y}`),
};

// ─── ══════════════════════════════════════════════════════════════════════ ───
//  PHASE 3 — ADVANCED APIs
// ─── ══════════════════════════════════════════════════════════════════════ ───

// HOSTEL  → prefix: /hostel
const HostelAPI = {
  create:         (d)        => API.post('/hostel', d),
  list:           (sid)      => API.get(`/hostel?school_id=${sid}`),
  delete:         (id)       => API.delete(`/hostel/${id}`),
  createRoom:     (d)        => API.post('/hostel/room', d),
  getRooms:       (sid,hid,avail) => API.get(`/hostel/room?school_id=${sid}${hid ? '&hostel_id=' + hid : ''}${avail ? '&available_only=true' : ''}`),
  allocate:       (d)        => API.post('/hostel/allocate', d),
  getAllocations:  (sid,hid)  => API.get(`/hostel/allocations?school_id=${sid}${hid ? '&hostel_id=' + hid : ''}`),
  checkout:       (id)       => API.patch(`/hostel/checkout/${id}`, {}),
  generateFees:   (d)        => API.post('/hostel/fee/generate', d),
  getFees:        (p)        => API.get('/hostel/fee', p),
  payFee:         (id,amt)   => API.patch(`/hostel/fee/${id}/pay`, { amount: amt }),
  createLeave:    (d)        => API.post('/hostel/leave', d),
  getLeaves:      (sid,st)   => API.get(`/hostel/leave?school_id=${sid}${st ? '&status=' + st : ''}`),
  actionLeave:    (id,d)     => API.patch(`/hostel/leave/${id}/action`, d),
  getStats:       (sid)      => API.get(`/hostel/stats/${sid}`),
};

// PAYROLL  → prefix: /payroll
const PayrollAPI = {
  getConfig:           (sid)      => API.get(`/payroll/config/${sid}`),
  saveConfig:          (d)        => API.post('/payroll/config', d),
  setSalaryStructure:  (d)        => API.post('/payroll/salary-structure', d),
  listSalaryStructures:(sid)      => API.get(`/payroll/salary-structure?school_id=${sid}`),
  getStaffSalary:      (staffId)  => API.get(`/payroll/salary-structure/${staffId}`),
  generate:            (d)        => API.post('/payroll/generate', d),
  list:                (sid,m,y)  => API.get(`/payroll?school_id=${sid}&month=${m}&year=${y}`),
  approve:             (id)       => API.patch(`/payroll/${id}/approve`, {}),
  markPaid:            (id,d)     => API.patch(`/payroll/${id}/mark-paid`, d),
  getPayslip:          (id)       => API.get(`/payroll/payslip/${id}`),
  getSummary:          (sid)      => API.get(`/payroll/summary/${sid}`),
};

// ADMISSIONS  → prefix: /admissions
const AdmissionsAPI = {
  getSettings:  (sid)    => API.get(`/admissions/settings/${sid}`),
  saveSettings: (d)      => API.post('/admissions/settings', d),
  apply:        (d)      => API.post('/admissions/apply', d),
  list:         (p)      => API.get('/admissions', p),
  get:          (id)     => API.get(`/admissions/${id}`),
  updateStatus: (id,d)   => API.patch(`/admissions/${id}/status`, d),
  getStats:     (sid)    => API.get(`/admissions/stats/${sid}`),
};

// CERTIFICATES  → prefix: /certificates
const CertAPI = {
  getTemplates: (sid)    => API.get(`/certificates/templates?school_id=${sid}`),
  issue:        (d)      => API.post('/certificates/issue', d),
  listIssued:   (p)      => API.get('/certificates/issued', p),
  preview:      (id)     => API.get(`/certificates/preview/${id}`),
};

// PARENT PORTAL  → prefix: /parent
const ParentAPI = {
  register:         (d)    => API.post('/parent/register', d),
  login:            (d)    => API.post('/parent/login', d),
  adminGetMessages: (sid)  => API.get(`/parent/admin/messages?school_id=${sid}`),
  adminMarkRead:    (id)   => API.patch(`/parent/admin/messages/${id}/read`, {}),
  adminGetParents:  (sid)  => API.get(`/parent/admin/parents?school_id=${sid}`),
};

const UserAdminAPI = {
  list:   (sid)    => API.get('/auth/users', sid ? { school_id: sid } : {}),
  create: (d)      => API.post('/auth/users', d),
  update: (id, d)  => API.put(`/auth/users/${id}`, d),
  roles:  ()       => API.get('/auth/roles'),
};


// ─── Convenience Aliases ─────────────────────────────────────────────────────
// Used by institution.html, fees.html, exams.html etc.

const AcademicYearAPI = {
  list:       (sid)  => API.get(`/institution/academic-year?school_id=${sid}`),
  create:     (d)    => API.post('/institution/academic-year', d),
  updateAY:   (id,d) => API.put(`/institution/academic-year/${id}`, d),
  deleteAY:   (id)   => API.delete(`/institution/academic-year/${id}`),
  setCurrent: (id)   => API.patch(`/institution/academic-year/${id}/set-current`, {}),
};

const ClassAPI = {
  list:        (sid, ayid) => API.get(`/institution/class?school_id=${sid}${ayid ? '&academic_year_id=' + ayid : ''}`),
  create:      (d)         => API.post('/institution/class', d),
  updateClass: (id,d)      => API.put(`/institution/class/${id}`, d),
  deleteClass: (id)        => API.delete(`/institution/class/${id}`),
};

const SubjectAPI = {
  list:   (sid, p = {}) => API.get('/institution/subject', { school_id: sid, ...p }),
  getMapping: (p)  => API.get('/institution/subject-mapping', p),
  saveMapping:(d)  => API.post('/institution/subject-mapping', d),
  create: (d)      => API.post('/institution/subject', d),
  update: (id,d)   => API.put(`/institution/subject/${id}`, d),
  delete: (id)     => API.delete(`/institution/subject/${id}`),
};

const GradingAPI = {
  list:   (sid)    => API.get(`/institution/grading-system?school_id=${sid}`),
  create: (d)      => API.post('/institution/grading-system', d),
  update: (id,d)   => API.put(`/institution/grading-system/${id}`, d),
  delete: (id)     => API.delete(`/institution/grading-system/${id}`),
};

const SectionAPI = {
  list:   (sid, cid) => API.get(`/institution/section?school_id=${sid}${cid ? '&classroom_id=' + cid : ''}`),
};

// ─── Init ─────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => { Toast._getC(); });
