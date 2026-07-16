# Teacher Dismissal Empty States Prototype Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one offline mini-program HTML prototype for the approved teacher dismissal empty states, with editable developer rule annotations.

**Architecture:** Copy the annotated-prototype shell to a temporary source, retain its rule-inspector runtime, and replace the sample product with a fixed mini-program phone plus an external state-review switch. Bundle the pinned Vue and Naive UI assets into one repository HTML, validate rule coverage, then exercise the result in a real browser.

**Tech Stack:** Vue 3 global build, Naive UI global build, ThorUI-style `tui-*` classes, HTML/CSS/JavaScript, Python validator and bundler, Playwright.

## Global Constraints

- Deliver exactly one final `.html`; keep the editable source only under `/tmp`.
- Target only 小程序; do not expose PC or APP switching.
- Keep all approved Chinese copy exact, including `12556166`.
- Empty states contain no refresh, navigation, telephone link, call action, or other product interaction.
- Keep the class row only in the missing-schedule state.
- No-class permission takes precedence when both abnormal conditions exist.
- Use ThorUI-style mobile classes and real Naive UI controls for review and rule editing.
- Preserve rule add, edit, delete, reorder, dynamic sections, local save, restore, and versioned export.
- The final HTML contains no remote dependency, fetch, network font, remote image, or vendor marker.

---

### Task 1: Create the annotated source

**Files:**
- Read: `docs/superpowers/specs/2026-07-16-teacher-empty-states-design.md`
- Copy: `/Users/szjxxiangmubu/Codex 项目/skills/design-annotated-prototype/skill/assets/prototype-shell.html`
- Create temporarily: `/tmp/teacher-empty-states.source.html`

**Interfaces:**
- Consumes: approved state names `no-class` and `no-schedule`, plus the shell rule-inspector runtime.
- Produces: a source with vendor markers, `activeState: Ref<'no-class'|'no-schedule'>`, fixed `activePlatform='mini'`, and contexts `P01`–`P04`.

- [ ] **Step 1: Copy the vendor shell**

~~~bash
cp '/Users/szjxxiangmubu/Codex 项目/skills/design-annotated-prototype/skill/assets/prototype-shell.html' '/tmp/teacher-empty-states.source.html'
~~~

Expected: the temporary file contains one Vue marker and one Naive UI marker.

- [ ] **Step 2: Replace sample state and data**

Keep the inspector variables and functions. Replace sample product state with:

~~~js
const activePlatform=ref('mini');
const activeState=ref('no-class');
const states=[
  {value:'no-class',label:'无班级权限'},
  {value:'no-schedule',label:'未设置放学时间'}
];
const currentClass={name:'一年级1.1班',teacher:'黄腾飞老师'};
~~~

Remove task rows, PC columns, modal/drawer state, sample overlays, and all sample task copy. Keep `activePlatform` fixed and hidden only because the supplied validator checks platform-state support.

- [ ] **Step 3: Replace the visible product template**

Use an external Naive UI button group for review switching. Inside the phone, render this exact product hierarchy:

~~~html
<main class="phone-stage mini-program" data-rule-context="P01" data-rule-id="P01-01">
  <div class="phone teacher-phone">
    <div class="status-bar"><span>17:25</span><span>◉ ◉ 5G ▮▮ 80</span></div>
    <div class="tui-navbar dismissal-navbar">
      <span class="home-icon">⌂</span><span>放学管理</span><span class="mini-capsule">•••　◉</span>
    </div>
    <section v-if="activeState==='no-schedule'" class="tui-list class-strip" data-rule-context="P02" data-rule-id="P02-01">
      <div class="tui-list-cell"><div><b>{{currentClass.name}}</b><span>{{currentClass.teacher}}</span></div><span class="chevron">›</span></div>
    </section>
    <div class="tui-page empty-page">
      <section v-if="activeState==='no-class'" class="tui-card tui-empty empty-card" data-rule-context="P03" data-rule-id="P03-01">
        <div class="empty-illustration" aria-hidden="true">▥　●</div>
        <h1>暂无可管理班级</h1>
        <p>当前账号尚未关联可管理的班级，请联系学校管理员开通权限。</p>
        <div class="service-copy">如需帮助，请联系客服电话：<strong>12556166</strong></div>
      </section>
      <section v-else class="tui-card tui-empty empty-card" data-rule-context="P04" data-rule-id="P04-01">
        <div class="empty-illustration schedule" aria-hidden="true">▦　◷</div>
        <h1>暂未设置放学时间</h1>
        <p>学校尚未配置放学时间，请联系学校管理员完成设置。</p>
        <div class="service-copy">如需帮助，请联系客服电话：<strong>12556166</strong></div>
      </section>
    </div>
  </div>
</main>
~~~

Expected: the state switch is outside `.teacher-phone\); the phone contains no buttons, links, click handlers, or role buttons.

- [ ] **Step 4: Apply the approved visual system**

Add CSS with these concrete values:

~~~css
:root{--brand:#74d680;--brand-deep:#51b965;--ink:#1c211e;--muted:#7d8580;--phone-bg:#f5f6f5}
.phone-stage{min-height:calc(100vh - 66px);padding:32px 20px 64px;background:#eef3ef}
.teacher-phone{width:390px;min-height:780px;border:1px solid #dfe5e1;border-radius:28px;background:var(--phone-bg)}
.status-bar{display:flex;justify-content:space-between;padding:14px 20px 10px;color:#fff;background:var(--brand);font-weight:700}
.dismissal-navbar{display:grid;grid-template-columns:72px 1fr 96px;align-items:center;min-height:66px;padding:0 14px 12px;color:#fff;background:var(--brand);font-size:20px;font-weight:500}
.dismissal-navbar .mini-capsule{position:static;width:auto;height:34px;padding:5px 10px;border:0;background:rgba(42,139,65,.34);font-size:14px}
.class-strip{border-radius:0;border-bottom:1px solid #eef1ef}
.class-strip .tui-list-cell{min-height:68px;padding:0 20px;font-size:16px}
.class-strip b{margin-right:10px;font-size:19px}.class-strip span{color:#59615c}.class-strip .chevron{font-size:30px;color:#9ba19d}
.empty-page{display:grid;place-items:start center;padding:54px 20px 40px}
.empty-card{width:100%;margin:0;padding:38px 24px 30px;text-align:center;box-shadow:0 10px 30px rgba(40,72,48,.06)}
.empty-illustration{display:grid;place-items:center;width:108px;height:94px;margin:0 auto 24px;color:var(--brand-deep);background:#e8f8eb;border-radius:48% 52% 46% 54%;font-size:34px}
.empty-card h1{margin:0 0 12px;font-size:22px}.empty-card p{margin:0 auto;max-width:285px;color:var(--muted);font-size:15px;line-height:1.75}
.service-copy{margin-top:24px;padding-top:20px;border-top:1px solid #edf1ee;color:#6f7772;font-size:14px}.service-copy strong{color:#3d8d4d;letter-spacing:.4px}
@media(max-width:480px){.prototype-top{align-items:flex-start;gap:10px;flex-direction:column}.phone-stage{padding:16px 8px 48px}.teacher-phone{width:min(390px,100%);border-radius:22px}}
~~~

Expected: the layout matches the reference page's green navigation, pale background, white rounded surface, restrained shadow, and mobile safe-area rhythm.

- [ ] **Step 5: Replace embedded rules**

Create exactly four context arrays:

- `P01-01 教师端放学管理页面框架`: navigation, mini-program framing, and no-class precedence.
- `P02-01 当前班级信息`: visible only with at least one manageable class; fixed review example `一年级1.1班 黄腾飞老师`.
- `P03-01 无班级权限空状态`: trigger, hidden class/schedule/action modules, exact copy, hotline, and no-interaction constraint.
- `P04-01 未设置放学时间空状态`: trigger, retained class row, hidden schedule/action modules, exact copy, hotline, and no-interaction constraint.

Each rule uses `{id,title,kind,sections:[{label,content}]}`; every section label and content is non-empty. Remove `M01`, `D01`, and all sample task rules.

- [ ] **Step 6: Validate the source**

~~~bash
python3 '/Users/szjxxiangmubu/Codex 项目/skills/design-annotated-prototype/skill/scripts/validate_prototype.py' '/tmp/teacher-empty-states.source.html' --allow-vendor-markers
~~~

Expected: `验证通过：/tmp/teacher-empty-states.source.html`.

### Task 2: Bundle and statically verify the deliverable

**Files:**
- Consume: `/tmp/teacher-empty-states.source.html`
- Create: `prototypes/教师端放学管理空状态标注原型.html`

**Interfaces:**
- Consumes: validated source with vendor markers.
- Produces: one offline HTML with embedded Vue, Naive UI, initial rules, and no network dependencies.

- [ ] **Step 1: Bundle pinned vendor assets**

~~~bash
python3 '/Users/szjxxiangmubu/Codex 项目/skills/design-annotated-prototype/skill/scripts/build_single_html.py' '/tmp/teacher-empty-states.source.html' 'prototypes/教师端放学管理空状态标注原型.html'
~~~

Expected: `已生成离线单文件`.

- [ ] **Step 2: Run final validation**

~~~bash
python3 '/Users/szjxxiangmubu/Codex 项目/skills/design-annotated-prototype/skill/scripts/validate_prototype.py' 'prototypes/教师端放学管理空状态标注原型.html'
~~~

Expected: validation passes with zero vendor-marker, remote-dependency, missing-token, missing-rule, or orphan-rule errors.

- [ ] **Step 3: Confirm the delivery contains one HTML**

~~~bash
find prototypes -maxdepth 1 -type f -name '*.html' -print
~~~

Expected: only `prototypes/教师端放学管理空状态标注原型.html`.

### Task 3: Exercise the prototype in a real browser

**Files:**
- Test: `prototypes/教师端放学管理空状态标注原型.html`
- Test export: a downloaded `*-v1.0.1.html` file under `/tmp`

**Interfaces:**
- Consumes: bundled offline HTML.
- Produces: evidence for both states, zero product interactions, rule editing, local persistence, restore, and versioned export.

- [ ] **Step 1: Open the absolute `file://` URL at 430 × 900**

Expected: the review toolbar and one phone are visible; the inspector is hidden.

- [ ] **Step 2: Assert the no-class state**

Visible: `放学管理`, `暂无可管理班级`, the approved explanation, and `12556166`.

Absent: `一年级1.1班`, `今日放学日程`, and `一键放学`.

- [ ] **Step 3: Assert the missing-schedule state**

Click external `未设置放学时间`.

Visible: `一年级1.1班`, `黄腾飞老师`, `暂未设置放学时间`, the approved explanation, and `12556166`.

Absent: `今日放学日程` and `一键放学`.

- [ ] **Step 4: Assert zero product actions**

Within `.teacher-phone`, count `button`, `a`, `[role="button"]`, and `[onclick]`.

Expected: zero in both states.

- [ ] **Step 5: Verify rule CRUD and persistence**

Open `查看规则`, edit `P03-01`, add section `验收备注 / 浏览器持久化验证`, save the rule, click `保存修改`, and reload.

Expected: the new section persists and typing retains focus. Then click `恢复初始`; the temporary section disappears.

- [ ] **Step 6: Verify versioned export**

Click `导出最新版 HTML`.

Expected: filename ends in `-v1.0.1.html`. Reopen it offline and confirm all four initial contexts remain editable.

- [ ] **Step 7: Capture both states**

Save full-page screenshots to:

~~~text
/tmp/teacher-empty-no-class.png
/tmp/teacher-empty-no-schedule.png
~~~

Expected: no overflow, clipped copy, overlapping capsule, or unsafe-area collision.

### Task 4: Final verification and commit

**Files:**
- Add: `prototypes/教师端放学管理空状态标注原型.html`
- Preserve unstaged: the user's existing `放学系统解决方案_一页版.pptx`

**Interfaces:**
- Consumes: successful static and browser verification.
- Produces: a commit containing only the final prototype.

- [ ] **Step 1: Re-run final validation**

~~~bash
python3 '/Users/szjxxiangmubu/Codex 项目/skills/design-annotated-prototype/skill/scripts/validate_prototype.py' 'prototypes/教师端放学管理空状态标注原型.html'
~~~

Expected: `验证通过` with zero errors.

- [ ] **Step 2: Inspect scope**

~~~bash
git diff --check
git status --short
~~~

Expected: the prototype is the only new task artifact; the existing PPT stays unstaged.

- [ ] **Step 3: Stage and inspect only the prototype**

~~~bash
git add 'prototypes/教师端放学管理空状态标注原型.html'
git diff --staged --stat
~~~

Expected: only the prototype HTML is staged.

- [ ] **Step 4: Commit**

~~~bash
git commit -m "feat(prototype): add teacher empty states"
~~~

Expected: commit succeeds without staging the unrelated PPT.
