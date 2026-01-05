const MAX_DIFF_LINES = 400;
const MONACO_BASE = window.MONACO_BASE || "https://cdn.jsdelivr.net/npm/monaco-editor@0.44.0/min";
const MODULES_REFRESH_INTERVAL_MS = 10000;
const FILE_PREVIEW_REF = "head";

const state = {
  diffMode: "all",
  status: null,
  config: null,
  gitTreeMode: "changed",
  gitTreeIncludeIgnored: false,
  gitTreeFiles: [],
  gitTreeFilesByPath: {},
  gitTreeSelections: {},
  gitTreeOrder: [],
  gitTreeExpanded: {},
  lastGitTreeSelection: null,
  filePreviewPath: null,
  branches: [],
  selectedBranch: null,
  commits: [],
  selectedCommit: null,
  modulesIndex: [],
  selectedModuleId: null,
  selectedModuleFile: null,
  moduleFileContent: "",
  moduleFileDirty: false,
  moduleFileKind: null,
  moduleItemsByFile: {},
  moduleItemSelections: {},
  moduleItemOrder: {},
  lastModuleSelection: null,
  modulesStale: false,
  modulesEnabled: false,
  exportTab: "entities",
  exportConfig: null,
  groupsData: null,
  selectedGroupObjectId: null,
};

const dom = {
  statusSummary: document.getElementById("status-summary"),
  statusMessage: document.getElementById("status-message"),
  statusRefresh: document.getElementById("status-refresh"),
  remoteRefresh: document.getElementById("remote-refresh"),
  commitMessage: document.getElementById("commit-message"),
  commitStaged: document.getElementById("commit-staged"),
  commitAll: document.getElementById("commit-all"),
  commitStatus: document.getElementById("commit-status"),
  pullBtn: document.getElementById("pull-btn"),
  pushBtn: document.getElementById("push-btn"),
  diffList: document.getElementById("diff-list"),
  diffMode: document.getElementById("diff-mode"),
  stageAll: document.getElementById("stage-all"),
  unstageAll: document.getElementById("unstage-all"),
  gitTree: document.getElementById("git-tree"),
  gitTreeMode: document.getElementById("git-tree-mode"),
  gitTreeIgnored: document.getElementById("git-tree-ignored"),
  gitTreeSelection: document.getElementById("git-tree-selection"),
  treeStageSelected: document.getElementById("tree-stage-selected"),
  treeUnstageSelected: document.getElementById("tree-unstage-selected"),
  fileViewer: document.getElementById("file-viewer"),
  fileViewerMeta: document.getElementById("file-viewer-meta"),
  fileViewerContent: document.getElementById("file-viewer-content"),
  fileViewerClose: document.getElementById("file-viewer-close"),
  fileViewerIgnore: document.getElementById("file-viewer-ignore"),
  branchSelect: document.getElementById("branch-select"),
  commitList: document.getElementById("commit-list"),
  commitMeta: document.getElementById("commit-meta"),
  commitDiffs: document.getElementById("commit-diffs"),
  resetCommit: document.getElementById("reset-commit"),
  configRemoteUrl: document.getElementById("config-remote-url"),
  configRemoteBranch: document.getElementById("config-remote-branch"),
  configGitUserName: document.getElementById("config-git-user-name"),
  configGitUserEmail: document.getElementById("config-git-user-email"),
  configWebhookPath: document.getElementById("config-webhook-path"),
  configPollInterval: document.getElementById("config-poll-interval"),
  configNotifications: document.getElementById("config-notifications"),
  configWebhookEnabled: document.getElementById("config-webhook-enabled"),
  configYamlModules: document.getElementById("config-yaml-modules"),
  configTheme: document.getElementById("config-ui-theme"),
  saveConfig: document.getElementById("save-config"),
  configStatus: document.getElementById("config-status"),
  sshStatus: document.getElementById("ssh-status"),
  sshPublicKey: document.getElementById("ssh-public-key"),
  sshInstructions: document.getElementById("ssh-instructions"),
  sshGenerateBtn: document.getElementById("ssh-generate-btn"),
  sshLoadBtn: document.getElementById("ssh-load-btn"),
  sshTestBtn: document.getElementById("ssh-test-btn"),
  sshTestStatus: document.getElementById("ssh-test-status"),
  modulesStatus: document.getElementById("modules-status"),
  modulesSyncBtn: document.getElementById("modules-sync-btn"),
  modulesPreviewBtn: document.getElementById("modules-preview-btn"),
  modulesPreviewBuild: document.getElementById("modules-preview-build"),
  modulesPreviewUpdate: document.getElementById("modules-preview-update"),
  modulesPreviewStatus: document.getElementById("modules-preview-status"),
  moduleSelect: document.getElementById("module-select"),
  moduleFileList: document.getElementById("module-file-list"),
  moduleSelectionCount: document.getElementById("module-selection-count"),
  moduleFileMeta: document.getElementById("module-file-meta"),
  moduleSaveBtn: document.getElementById("module-save-btn"),
  moduleDeleteBtn: document.getElementById("module-delete-btn"),
  moduleMoveBtn: document.getElementById("module-move-btn"),
  moduleUnassignBtn: document.getElementById("module-unassign-btn"),
  moduleDeleteItemsBtn: document.getElementById("module-delete-items-btn"),
  moduleEditor: document.getElementById("module-editor"),
  moduleEditorStatus: document.getElementById("module-editor-status"),
  moduleMoveModal: document.getElementById("module-move-modal"),
  moduleMoveClose: document.getElementById("module-move-close"),
  moduleMoveCancel: document.getElementById("module-move-cancel"),
  moduleMoveConfirm: document.getElementById("module-move-confirm"),
  moduleMovePackage: document.getElementById("module-move-package"),
  moduleMoveNewPackage: document.getElementById("module-move-new-package"),
  moduleMoveOneOff: document.getElementById("module-move-one-off"),
  moduleMoveSummary: document.getElementById("module-move-summary"),
  exportRunBtn: document.getElementById("export-run-btn"),
  exportStatus: document.getElementById("export-status"),
  exportBlacklist: document.getElementById("export-blacklist"),
  exportSaveConfig: document.getElementById("export-save-config"),
  exportFileMeta: document.getElementById("export-file-meta"),
  exportTable: document.getElementById("export-table"),
  exportConfigEntities: document.getElementById("export-config-entities"),
  exportConfigOther: document.getElementById("export-config-other"),
  groupsRestartBanner: document.getElementById("groups-restart-banner"),
  groupsRestartAck: document.getElementById("groups-restart-ack"),
  groupsConfigWarning: document.getElementById("groups-config-warning"),
  groupsObjectId: document.getElementById("groups-object-id"),
  groupsName: document.getElementById("groups-name"),
  groupsMembers: document.getElementById("groups-members"),
  groupsDestinationType: document.getElementById("groups-destination-type"),
  groupsDestinationPackage: document.getElementById("groups-destination-package"),
  groupsDestinationOneOff: document.getElementById("groups-destination-one-off"),
  groupsPackageName: document.getElementById("groups-package-name"),
  groupsOneOffFilename: document.getElementById("groups-one-off-filename"),
  groupsSave: document.getElementById("groups-save"),
  groupsDelete: document.getElementById("groups-delete"),
  groupsClear: document.getElementById("groups-clear"),
  groupsStatus: document.getElementById("groups-status"),
  groupsRefresh: document.getElementById("groups-refresh"),
  groupsShowUnmanaged: document.getElementById("groups-show-unmanaged"),
  groupsShowIgnored: document.getElementById("groups-show-ignored"),
  groupsManagedTable: document.getElementById("groups-managed-table"),
  groupsUnmanagedSection: document.getElementById("groups-unmanaged-section"),
  groupsUnmanagedTable: document.getElementById("groups-unmanaged-table"),
  cliInstallBtn: document.getElementById("cli-install"),
  cliOverwrite: document.getElementById("cli-overwrite"),
  cliStatus: document.getElementById("cli-status"),
  toast: document.getElementById("toast"),
};

let toastTimer = null;
let moduleEditor = null;
let moduleEditorTextarea = null;
let moduleEditorPromise = null;
let moduleEditorSetting = false;
let moduleRefreshTimer = null;
let moduleIndexLoading = false;
let diff2HtmlPromise = null;

function qs(selector, scope = document) {
  return scope.querySelector(selector);
}

function qsa(selector, scope = document) {
  return Array.from(scope.querySelectorAll(selector));
}

function showToast(message) {
  if (!dom.toast) {
    return;
  }
  dom.toast.textContent = message;
  dom.toast.classList.add("is-visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    dom.toast.classList.remove("is-visible");
  }, 3200);
}

async function requestJSON(url, options = {}) {
  const headers = options.headers || {};
  if (!(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  const response = await fetch(url, { ...options, headers });
  let payload = {};
  try {
    payload = await response.json();
  } catch (err) {
    payload = {};
  }
  if (!response.ok) {
    throw new Error(payload.detail || payload.status || "Request failed");
  }
  return payload;
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme || "system";
  setEditorTheme();
}

function getEditorTheme() {
  const theme = document.documentElement.dataset.theme;
  if (theme === "dark") {
    return "vs-dark";
  }
  if (theme === "light") {
    return "vs";
  }
  if (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) {
    return "vs-dark";
  }
  return "vs";
}

function setEditorTheme() {
  if (!moduleEditor || !window.monaco || !window.monaco.editor) {
    return;
  }
  window.monaco.editor.setTheme(getEditorTheme());
}

function setTab(tab) {
  qsa(".tab-btn[data-tab]").forEach((btn) => {
    btn.classList.toggle("is-active", btn.dataset.tab === tab);
  });
  qsa(".tab-panel").forEach((panel) => {
    panel.classList.toggle("is-active", panel.id === `tab-${tab}`);
  });
  if (tab === "modules" && moduleEditor) {
    setTimeout(() => moduleEditor.layout(), 0);
  }
  if (tab === "modules") {
    startModulesRefresh();
  } else {
    stopModulesRefresh();
  }
  if (tab === "exports") {
    loadExportConfig();
    setExportTab(state.exportTab);
  }
  if (tab === "groups") {
    loadGroupsData();
  }
  if (tab === "git") {
    loadGitFiles();
  }
}

function isModulesTabActive() {
  const panel = document.getElementById("tab-modules");
  return panel ? panel.classList.contains("is-active") : false;
}

function startModulesRefresh() {
  if (!moduleRefreshTimer) {
    moduleRefreshTimer = setInterval(() => {
      if (!isModulesTabActive()) {
        return;
      }
      loadModulesIndex({ allowDirty: false });
    }, MODULES_REFRESH_INTERVAL_MS);
  }
  loadModulesIndex({ allowDirty: false });
}

function stopModulesRefresh() {
  if (!moduleRefreshTimer) {
    return;
  }
  clearInterval(moduleRefreshTimer);
  moduleRefreshTimer = null;
}

function updateModulesStatus(enabled) {
  state.modulesEnabled = enabled;
  dom.modulesStatus.textContent = enabled
    ? "YAML Modules sync is enabled."
    : "YAML Modules sync is disabled in add-on options.";
  dom.modulesSyncBtn.disabled = !enabled;
  if (dom.modulesPreviewBtn) {
    dom.modulesPreviewBtn.disabled = !enabled;
  }
  updateModuleActionButtons();
}

function renderSummaryItem(label, value) {
  const item = document.createElement("div");
  item.className = "summary-item";
  const span = document.createElement("span");
  span.textContent = label;
  const strong = document.createElement("strong");
  strong.textContent = value;
  item.append(span, strong);
  return item;
}

function formatRemoteStatus(remoteStatus) {
  if (!remoteStatus || !remoteStatus.configured) {
    return "Not configured";
  }
  if (remoteStatus.error) {
    return remoteStatus.error;
  }
  const ahead = remoteStatus.ahead || 0;
  const behind = remoteStatus.behind || 0;
  if (!ahead && !behind) {
    return "Up to date";
  }
  if (ahead && behind) {
    return `Ahead ${ahead}, behind ${behind}`;
  }
  if (ahead) {
    return `Ahead by ${ahead}`;
  }
  return `Behind by ${behind}`;
}

function renderStatus(data) {
  dom.statusSummary.innerHTML = "";
  dom.statusSummary.append(
    renderSummaryItem("Branch", data.branch || "-"),
    renderSummaryItem("Remote", data.remote || "Not configured"),
    renderSummaryItem("Remote Sync", formatRemoteStatus(data.remote_status)),
    renderSummaryItem("Staged", String(data.staged_count || 0)),
    renderSummaryItem("Unstaged", String(data.unstaged_count || 0)),
    renderSummaryItem("Untracked", String(data.untracked_count || 0)),
    renderSummaryItem("Pending", String((data.pending || []).length))
  );

  if (data.commits && data.commits.length) {
    dom.statusSummary.append(
      renderSummaryItem("Latest Commit", data.commits[0].subject)
    );
  }

  const needsRemote = !data.remote;
  dom.pullBtn.disabled = needsRemote;
  dom.pushBtn.disabled = needsRemote;
  dom.remoteRefresh.disabled = needsRemote;
  dom.statusMessage.textContent = needsRemote
    ? "Remote is not configured. Push and pull are disabled."
    : "";

  updateModulesStatus(Boolean(data.yaml_modules_enabled));
}

function setDiffMode(mode) {
  state.diffMode = mode;
  qsa("#diff-mode .segmented-btn").forEach((el) =>
    el.classList.toggle("is-active", el.dataset.mode === mode)
  );
  if (state.status) {
    renderDiffList(state.status.changes || []);
  }
}

function matchesDiffMode(change) {
  if (state.diffMode === "staged") {
    return change.staged;
  }
  if (state.diffMode === "unstaged") {
    return change.unstaged || change.untracked;
  }
  return true;
}

function buildChangeLabel(change) {
  if (change.rename_from) {
    return `${change.rename_from} -> ${change.path}${change.is_dir ? "/" : ""}`;
  }
  return `${change.path}${change.is_dir ? "/" : ""}`;
}

function isBinaryDiff(diffText) {
  return diffText.includes("Binary files") || diffText.includes("GIT binary patch");
}

function loadDiff2Html() {
  if (window.Diff2Html && typeof window.Diff2Html.html === "function") {
    return Promise.resolve(window.Diff2Html);
  }
  if (!window.require) {
    return Promise.resolve(null);
  }
  if (!diff2HtmlPromise) {
    diff2HtmlPromise = new Promise((resolve, reject) => {
      window.require(
        ["Diff2Html"],
        (diff2Html) => {
          if (diff2Html && typeof diff2Html.html === "function") {
            window.Diff2Html = diff2Html;
            resolve(diff2Html);
            return;
          }
          resolve(null);
        },
        (err) => reject(err)
      );
    }).catch(() => {
      diff2HtmlPromise = null;
      return null;
    });
  }
  return diff2HtmlPromise;
}

async function loadDiff(details, options) {
  if (details.dataset.loaded === "true" && !options.force) {
    return;
  }
  const body = qs(".diff-body", details);
  body.innerHTML = "Loading diff...";
  const url = new URL(options.endpoint, window.location.origin);
  Object.entries(options.query).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      url.searchParams.set(key, String(value));
    }
  });
  try {
    const data = await requestJSON(url.pathname + url.search);
    if (!data.diff || !data.diff.trim()) {
      body.innerHTML = "<div class=\"diff-placeholder\">No diff available.</div>";
    } else if (isBinaryDiff(data.diff)) {
      body.innerHTML = "<div class=\"diff-placeholder\">Binary file changed. Diff not available.</div>";
    } else {
      const diff2Html = await loadDiff2Html();
      if (!diff2Html || typeof diff2Html.html !== "function") {
        body.innerHTML = "<div class=\"diff-placeholder\">Diff viewer failed to load.</div>";
      } else {
        body.innerHTML = diff2Html.html(data.diff, {
          inputFormat: "diff",
          outputFormat: "side-by-side",
          drawFileList: false,
          matching: "lines",
        });
      }
    }

    if (data.truncated) {
      const loadMore = document.createElement("button");
      loadMore.className = "btn";
      loadMore.textContent = `Load full diff (${data.total_lines} lines)`;
      loadMore.addEventListener("click", async (event) => {
        event.stopPropagation();
        loadMore.disabled = true;
        await loadDiff(details, {
          endpoint: options.endpoint,
          query: { ...options.query, max_lines: "" },
          force: true,
        });
      });
      body.append(loadMore);
    }
  } catch (err) {
    body.innerHTML = `<div class=\"diff-placeholder\">${err.message}</div>`;
  }
  details.dataset.loaded = "true";
}

function createDiffCard(change, context) {
  const details = document.createElement("details");
  details.className = "diff-card";
  details.dataset.path = change.path;

  const summary = document.createElement("summary");

  const title = document.createElement("div");
  title.className = "diff-title";
  const fileLine = document.createElement("div");
  fileLine.textContent = buildChangeLabel(change);
  const meta = document.createElement("div");
  meta.className = "diff-meta";

  if (change.staged) {
    const chip = document.createElement("span");
    chip.className = "chip staged";
    chip.textContent = "Staged";
    meta.append(chip);
  }
  if (change.unstaged) {
    const chip = document.createElement("span");
    chip.className = "chip unstaged";
    chip.textContent = "Unstaged";
    meta.append(chip);
  }
  if (change.untracked) {
    const chip = document.createElement("span");
    chip.className = "chip untracked";
    chip.textContent = "Untracked";
    meta.append(chip);
  }
  if (context === "commit" && change.status) {
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.textContent = change.status;
    meta.append(chip);
  }

  title.append(fileLine, meta);
  summary.append(title);

  if (context === "status") {
    const actions = document.createElement("div");
    actions.className = "diff-actions";
    if (change.unstaged || change.untracked) {
      const stageBtn = document.createElement("button");
      stageBtn.className = "btn";
      stageBtn.textContent = "Stage";
      stageBtn.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        stageFiles([change.path]);
      });
      actions.append(stageBtn);
    }
    if (change.staged) {
      const unstageBtn = document.createElement("button");
      unstageBtn.className = "btn";
      unstageBtn.textContent = "Unstage";
      unstageBtn.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        unstageFiles([change.path]);
      });
      actions.append(unstageBtn);
    }
    const viewBtn = document.createElement("button");
    viewBtn.className = "btn";
    viewBtn.textContent = "View file";
    viewBtn.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      openFilePreview(change.path);
    });
    actions.append(viewBtn);

    const ignoreBtn = document.createElement("button");
    ignoreBtn.className = "btn";
    ignoreBtn.textContent = "Ignore";
    ignoreBtn.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      toggleGitignore(change.path, ignoreBtn);
    });
    actions.append(ignoreBtn);
    updateIgnoreButton(ignoreBtn, change.path);
    summary.append(actions);
  }

  details.append(summary);

  const body = document.createElement("div");
  body.className = "diff-body";
  body.innerHTML = "<div class=\"diff-placeholder\">Expand to load diff.</div>";
  details.append(body);

  details.addEventListener("toggle", () => {
    if (!details.open) {
      return;
    }
    if (change.is_dir && change.untracked) {
      body.innerHTML = "<div class=\"diff-placeholder\">New directory (untracked).</div>";
      details.dataset.loaded = "true";
      return;
    }
    if (context === "commit") {
      loadDiff(details, {
        endpoint: "/api/commit/diff",
        query: {
          sha: change.sha,
          path: change.path,
          max_lines: MAX_DIFF_LINES,
        },
      });
      return;
    }
    loadDiff(details, {
      endpoint: "/api/diff",
      query: {
        path: change.path,
        mode: state.diffMode,
        max_lines: MAX_DIFF_LINES,
        untracked: change.untracked ? "true" : "",
      },
    });
  });

  return details;
}

function renderDiffList(changes) {
  dom.diffList.innerHTML = "";
  const filtered = changes.filter(matchesDiffMode);
  if (!filtered.length) {
    dom.diffList.innerHTML = "<div class=\"diff-placeholder\">No diffs for this view.</div>";
    return;
  }
  filtered.forEach((change) => {
    dom.diffList.append(createDiffCard(change, "status"));
  });
}

function updateGitTreeSelectionCount() {
  if (!dom.gitTreeSelection) {
    return;
  }
  const count = Object.keys(state.gitTreeSelections).length;
  dom.gitTreeSelection.textContent =
    count === 0 ? "No files selected." : `${count} file${count === 1 ? "" : "s"} selected.`;
  updateGitTreeActionButtons();
}

function updateGitTreeActionButtons() {
  if (!dom.treeStageSelected || !dom.treeUnstageSelected) {
    return;
  }
  const selections = Object.values(state.gitTreeSelections);
  const canStage = selections.some((entry) => entry.unstaged || entry.untracked);
  const canUnstage = selections.some((entry) => entry.staged);
  dom.treeStageSelected.disabled = !canStage;
  dom.treeUnstageSelected.disabled = !canUnstage;
}

function setGitTreeSelection(items) {
  state.gitTreeSelections = {};
  items.forEach((item) => {
    state.gitTreeSelections[item.path] = item;
  });
  state.lastGitTreeSelection = items.length ? items[items.length - 1].path : null;
  syncGitTreeSelectionUI();
}

function toggleGitTreeSelection(item) {
  if (state.gitTreeSelections[item.path]) {
    delete state.gitTreeSelections[item.path];
  } else {
    state.gitTreeSelections[item.path] = item;
  }
  state.lastGitTreeSelection = item.path;
  syncGitTreeSelectionUI();
}

function selectGitTreeRange(targetPath) {
  const order = state.gitTreeOrder || [];
  if (!order.length) {
    return;
  }
  const startPath = state.lastGitTreeSelection;
  if (!startPath) {
    return;
  }
  const startIndex = order.indexOf(startPath);
  const endIndex = order.indexOf(targetPath);
  if (startIndex < 0 || endIndex < 0) {
    return;
  }
  const [from, to] = startIndex < endIndex ? [startIndex, endIndex] : [endIndex, startIndex];
  const selection = order
    .slice(from, to + 1)
    .map((path) => state.gitTreeFilesByPath[path])
    .filter(Boolean);
  setGitTreeSelection(selection);
}

function syncGitTreeSelectionUI() {
  if (!dom.gitTree) {
    return;
  }
  qsa(".tree-row[data-selectable=\"true\"]", dom.gitTree).forEach((row) => {
    row.classList.toggle("is-selected", Boolean(state.gitTreeSelections[row.dataset.path]));
  });
  updateGitTreeSelectionCount();
}

function handleTreeSelection(entry, event) {
  const isRange = event.shiftKey;
  const isToggle = event.metaKey || event.ctrlKey;
  if (isRange) {
    selectGitTreeRange(entry.path);
  } else if (isToggle) {
    toggleGitTreeSelection(entry);
  } else {
    setGitTreeSelection([entry]);
  }
  return { isRange, isToggle };
}

function buildTree(files) {
  const root = { name: "", path: "", dirs: {}, files: [] };
  files.forEach((entry) => {
    if (!entry.path) {
      return;
    }
    const parts = entry.path.split("/");
    let current = root;
    parts.forEach((part, index) => {
      if (!part) {
        return;
      }
      const isLast = index === parts.length - 1;
      if (isLast) {
        if (entry.is_dir) {
          if (!current.dirs[part]) {
            const nextPath = current.path ? `${current.path}/${part}` : part;
            current.dirs[part] = { name: part, path: nextPath, dirs: {}, files: [], entry: null };
          }
          current.dirs[part].entry = entry;
        } else {
          current.files.push({ ...entry, name: part });
        }
      } else {
        if (!current.dirs[part]) {
          const nextPath = current.path ? `${current.path}/${part}` : part;
          current.dirs[part] = { name: part, path: nextPath, dirs: {}, files: [], entry: null };
        }
        current = current.dirs[part];
      }
    });
  });
  return root;
}

function renderTreeNode(node, depth, order) {
  const container = document.createElement("div");
  const dirNames = Object.keys(node.dirs).sort();
  dirNames.forEach((name) => {
    const child = node.dirs[name];
    const entry = child.entry || null;
    const expanded =
      state.gitTreeExpanded[child.path] === undefined
        ? true
        : state.gitTreeExpanded[child.path];
    const row = document.createElement("div");
    row.className = "tree-row";
    row.style.setProperty("--depth", depth);
    row.dataset.kind = "dir";
    row.dataset.path = child.path;
    if (entry) {
      row.dataset.selectable = "true";
    }

    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "tree-toggle";
    toggle.textContent = expanded ? "v" : ">";
    toggle.addEventListener("click", (event) => {
      event.stopPropagation();
      state.gitTreeExpanded[child.path] = !expanded;
      renderGitTree(state.gitTreeFiles);
    });

    const nameSpan = document.createElement("div");
    nameSpan.className = "tree-name";
    nameSpan.textContent = entry && entry.is_dir ? `${name}/` : name;

    const icon = document.createElement("span");
    icon.className = "material-symbols-outlined tree-icon";
    icon.textContent = expanded ? "folder_open" : "folder";

    row.append(toggle, icon, nameSpan);

    if (entry) {
      const chips = [];
      if (entry.staged) {
        chips.push(["staged", "Staged"]);
      }
      if (entry.unstaged) {
        chips.push(["unstaged", "Unstaged"]);
      }
      if (entry.untracked) {
        chips.push(["untracked", "Untracked"]);
      }
      if (entry.ignored) {
        chips.push(["ignored", "Ignored"]);
      }
      if (!chips.length && entry.clean) {
        chips.push(["clean", "Clean"]);
      }
      chips.forEach(([className, label]) => {
        const chip = document.createElement("span");
        chip.className = `tree-chip ${className}`;
        chip.textContent = label;
        row.append(chip);
      });
      row.addEventListener("click", (event) => {
        const { isRange, isToggle } = handleTreeSelection(entry, event);
        if (!isRange && !isToggle) {
          scrollToDiff(entry);
        }
      });
      order.push(entry.path);
    } else {
      row.addEventListener("click", () => {
      state.gitTreeExpanded[child.path] = !expanded;
      renderGitTree(state.gitTreeFiles);
    });
    }

    container.append(row);

    if (expanded) {
      const childContainer = renderTreeNode(child, depth + 1, order);
      container.append(childContainer);
    }
  });

  const sortedFiles = node.files.sort((a, b) => a.name.localeCompare(b.name));
  sortedFiles.forEach((entry) => {
    const row = document.createElement("div");
    row.className = "tree-row";
    row.style.setProperty("--depth", depth);
    row.dataset.kind = "file";
    row.dataset.path = entry.path;
    row.dataset.selectable = "true";

    const toggle = document.createElement("span");
    toggle.className = "tree-toggle is-hidden";
    toggle.textContent = "";

    const icon = document.createElement("span");
    icon.className = "material-symbols-outlined tree-icon";
    icon.textContent = "description";

    const nameSpan = document.createElement("div");
    nameSpan.className = "tree-name";
    nameSpan.textContent = entry.name;

    row.append(toggle, icon, nameSpan);

    const chips = [];
    if (entry.staged) {
      chips.push(["staged", "Staged"]);
    }
    if (entry.unstaged) {
      chips.push(["unstaged", "Unstaged"]);
    }
    if (entry.untracked) {
      chips.push(["untracked", "Untracked"]);
    }
    if (entry.ignored) {
      chips.push(["ignored", "Ignored"]);
    }
    if (!chips.length && entry.clean) {
      chips.push(["clean", "Clean"]);
    }
    chips.forEach(([className, label]) => {
      const chip = document.createElement("span");
      chip.className = `tree-chip ${className}`;
      chip.textContent = label;
      row.append(chip);
    });

    row.addEventListener("click", (event) => {
      const { isRange, isToggle } = handleTreeSelection(entry, event);
      if (!isRange && !isToggle) {
        if (entry.staged || entry.unstaged || entry.untracked) {
          scrollToDiff(entry);
        } else {
          openFilePreview(entry.path);
        }
      }
    });
    container.append(row);
    order.push(entry.path);
  });

  return container;
}

function renderGitTree(files) {
  if (!dom.gitTree) {
    return;
  }
  dom.gitTree.innerHTML = "";
  if (!files.length) {
    state.gitTreeSelections = {};
    state.gitTreeOrder = [];
    updateGitTreeSelectionCount();
    dom.gitTree.innerHTML = "<div class=\"diff-placeholder\">No files found.</div>";
    return;
  }
  const tree = buildTree(files);
  const order = [];
  const container = renderTreeNode(tree, 0, order);
  dom.gitTree.append(container);
  state.gitTreeOrder = order;
  syncGitTreeSelectionUI();
}

async function loadGitFiles() {
  if (!dom.gitTree) {
    return;
  }
  const mode = state.gitTreeMode;
  const includeIgnored = state.gitTreeIncludeIgnored;
  dom.gitTree.innerHTML = "<div class=\"diff-placeholder\">Loading files...</div>";
  try {
    const data = await requestJSON(
      `/api/git/files?mode=${encodeURIComponent(mode)}&include_ignored=${includeIgnored}`
    );
    const files = data.files || [];
    const byPath = {};
    files.forEach((entry) => {
      byPath[entry.path] = entry;
    });
    state.gitTreeFiles = files;
    state.gitTreeFilesByPath = byPath;
    state.gitTreeSelections = Object.fromEntries(
      Object.entries(state.gitTreeSelections).filter(([path]) => byPath[path])
    );
    renderGitTree(files);
  } catch (err) {
    dom.gitTree.innerHTML = `<div class="diff-placeholder">${err.message}</div>`;
  }
}

function escapeSelector(value) {
  const str = String(value);

  // Browser-safe AND SSR/Node-safe
  if (typeof CSS !== "undefined" && typeof CSS.escape === "function") {
    return CSS.escape(str);
  }

  // Fallback: handle a few important CSS identifier edge cases
  return str
    .replace(/\0/g, "\uFFFD") // NULL isn't allowed; replace it
    // If it starts with a digit, or "-digit", escape the digit as a hex codepoint (\30 .. \39)
    .replace(/^(-?\d)/, (m) => (m[0] === "-" ? `-\\3${m[1]} ` : `\\3${m[0]} `))
    .replace(/^-$/, "\\-") // lone "-" is special
    // Then escape anything that's not a typical identifier char
    .replace(/[^a-zA-Z0-9_-]/g, (ch) => `\\${ch}`);
}

function openDiffCard(path) {
  if (!dom.diffList) {
    return;
  }
  const selector = `.diff-card[data-path="${escapeSelector(path)}"]`;
  const card = qs(selector, dom.diffList);
  if (!card) {
    return;
  }
  card.open = true;
  card.scrollIntoView({ behavior: "smooth", block: "start" });
}

function scrollToDiff(entry) {
  if (!entry) {
    return;
  }
  let nextMode = state.diffMode;
  if (entry.staged && state.diffMode === "unstaged") {
    nextMode = "all";
  }
  if ((entry.unstaged || entry.untracked) && state.diffMode === "staged") {
    nextMode = "all";
  }
  if (nextMode !== state.diffMode) {
    setDiffMode(nextMode);
    setTimeout(() => openDiffCard(entry.path), 0);
    return;
  }
  openDiffCard(entry.path);
}

async function updateIgnoreButton(button, path) {
  if (!button) {
    return;
  }
  button.disabled = true;
  button.dataset.path = path;
  button.dataset.ignored = "false";
  button.textContent = "Ignore";
  try {
    const status = await requestJSON(
      `/api/gitignore/status?path=${encodeURIComponent(path)}`
    );
    button.dataset.ignored = status.ignored ? "true" : "false";
    button.textContent = status.ignored ? "Unignore" : "Ignore";
  } catch (err) {
    button.textContent = "Ignore";
  } finally {
    button.disabled = false;
  }
}

async function toggleGitignore(path, button) {
  if (!path) {
    return;
  }
  if (button) {
    button.disabled = true;
  }
  try {
    const data = await requestJSON("/api/gitignore/toggle", {
      method: "POST",
      body: JSON.stringify({ path, action: "toggle" }),
    });
    let message = data.message || "Updated .gitignore";
    if (data.tracked) {
      message = `${message} (Tracked files still show diffs.)`;
    }
    showToast(message);
    await loadStatus();
    if (button) {
      await updateIgnoreButton(button, path);
    }
  } catch (err) {
    showToast(err.message);
  } finally {
    if (button) {
      button.disabled = false;
    }
  }
}

function closeFilePreview() {
  if (!dom.fileViewer) {
    return;
  }
  dom.fileViewer.classList.add("is-hidden");
  dom.fileViewerContent.textContent = "";
  dom.fileViewerMeta.textContent = "";
  state.filePreviewPath = null;
}

async function openFilePreview(path) {
  if (!dom.fileViewer || !dom.fileViewerContent || !dom.fileViewerMeta) {
    return;
  }
  state.filePreviewPath = path;
  dom.fileViewer.classList.remove("is-hidden");
  dom.fileViewerMeta.textContent = "Loading preview...";
  dom.fileViewerContent.textContent = "";
  if (dom.fileViewerIgnore) {
    updateIgnoreButton(dom.fileViewerIgnore, path);
  }
  try {
    const data = await requestJSON(
      `/api/git/file?path=${encodeURIComponent(path)}&ref=${FILE_PREVIEW_REF}`
    );
    const meta = [`${data.path}`];
    if (typeof data.size_bytes === "number") {
      meta.push(`${data.size_bytes} bytes`);
    }
    if (data.truncated) {
      meta.push("truncated");
    }
    dom.fileViewerMeta.textContent = meta.join(" | ");
    if (data.is_binary) {
      dom.fileViewerContent.textContent = "Binary file; preview not available.";
      return;
    }
    dom.fileViewerContent.textContent = data.content || "";
  } catch (err) {
    dom.fileViewerMeta.textContent = "Unable to load preview.";
    dom.fileViewerContent.textContent = err.message;
  }
}

async function loadStatus() {
  try {
    const data = await requestJSON("/api/status");
    state.status = data;
    renderStatus(data);
    renderDiffList(data.changes || []);
    await loadGitFiles();
  } catch (err) {
    dom.statusMessage.textContent = err.message;
  }
}

async function refreshRemoteStatus() {
  try {
    const data = await requestJSON("/api/remote/status?refresh=true");
    if (state.status) {
      state.status.remote_status = data;
      renderStatus(state.status);
    }
  } catch (err) {
    dom.statusMessage.textContent = err.message;
  }
}

async function stageFiles(files) {
  if (!files.length) {
    return;
  }
  try {
    await requestJSON("/api/stage", {
      method: "POST",
      body: JSON.stringify({ files }),
    });
    showToast("Staged changes");
    await loadStatus();
  } catch (err) {
    showToast(err.message);
  }
}

async function unstageFiles(files) {
  if (!files.length) {
    return;
  }
  try {
    await requestJSON("/api/unstage", {
      method: "POST",
      body: JSON.stringify({ files }),
    });
    showToast("Unstaged changes");
    await loadStatus();
  } catch (err) {
    showToast(err.message);
  }
}

async function commitChanges(includeUnstaged) {
  const message = dom.commitMessage.value.trim();
  if (!message) {
    showToast("Commit message required");
    return;
  }
  try {
    await requestJSON("/api/commit", {
      method: "POST",
      body: JSON.stringify({ message, include_unstaged: includeUnstaged }),
    });
    dom.commitMessage.value = "";
    showToast("Committed changes");
    await loadStatus();
  } catch (err) {
    showToast(err.message);
  }
}

async function pullChanges() {
  try {
    const data = await requestJSON("/api/pull", { method: "POST" });
    showToast(data.changes && data.changes.length ? "Pulled updates" : "Already up to date");
    await loadStatus();
  } catch (err) {
    showToast(err.message);
  }
}

async function pushChanges() {
  try {
    const data = await requestJSON("/api/push", { method: "POST" });
    const branchInfo = data.branch ? ` to ${data.branch}` : "";
    showToast(`Pushed${branchInfo}`);
    await loadStatus();
  } catch (err) {
    showToast(err.message);
  }
}

async function loadBranches() {
  try {
    const data = await requestJSON("/api/branches");
    state.branches = data.branches || [];
    state.selectedBranch = data.current || state.branches[0];
    dom.branchSelect.innerHTML = "";
    state.branches.forEach((branch) => {
      const option = document.createElement("option");
      option.value = branch;
      option.textContent = branch;
      dom.branchSelect.append(option);
    });
    if (state.selectedBranch) {
      dom.branchSelect.value = state.selectedBranch;
      await loadCommits(state.selectedBranch);
    }
  } catch (err) {
    showToast(err.message);
  }
}

function renderCommitList(commits) {
  dom.commitList.innerHTML = "";
  if (!commits.length) {
    dom.commitList.innerHTML = "<div class=\"diff-placeholder\">No commits found.</div>";
    return;
  }
  commits.forEach((commit) => {
    const item = document.createElement("div");
    item.className = "commit-item";
    const subject = document.createElement("div");
    subject.textContent = commit.subject;
    const meta = document.createElement("div");
    meta.className = "note";
    meta.textContent = `${commit.sha} - ${commit.author} - ${commit.date}`;
    item.append(subject, meta);
    item.addEventListener("click", () => {
      qsa(".commit-item").forEach((el) => el.classList.remove("is-active"));
      item.classList.add("is-active");
      loadCommitDetails(commit);
    });
    dom.commitList.append(item);
  });
}

async function loadCommits(branch) {
  try {
    const data = await requestJSON(`/api/commits?branch=${encodeURIComponent(branch)}&limit=50`);
    state.commits = data.commits || [];
    renderCommitList(state.commits);
    dom.commitMeta.textContent = "Select a commit to inspect its diff.";
    dom.commitDiffs.innerHTML = "";
    dom.resetCommit.disabled = true;
  } catch (err) {
    showToast(err.message);
  }
}

async function loadCommitDetails(commit) {
  state.selectedCommit = commit;
  dom.commitMeta.textContent = `${commit.sha} - ${commit.subject}`;
  dom.commitDiffs.innerHTML = "<div class=\"diff-placeholder\">Loading diffs...</div>";
  dom.resetCommit.disabled = false;
  try {
    const files = await requestJSON(`/api/commit/files?sha=${commit.sha_full}`);
    dom.commitDiffs.innerHTML = "";
    if (!files.files.length) {
      dom.commitDiffs.innerHTML = "<div class=\"diff-placeholder\">No diff for this commit.</div>";
      return;
    }
    files.files.forEach((file) => {
      dom.commitDiffs.append(
        createDiffCard({
          ...file,
          sha: commit.sha_full,
        }, "commit")
      );
    });
  } catch (err) {
    dom.commitDiffs.innerHTML = `<div class=\"diff-placeholder\">${err.message}</div>`;
  }
}

async function resetToCommit() {
  if (!state.selectedCommit) {
    return;
  }
  const sha = state.selectedCommit.sha_full || state.selectedCommit.sha;
  const status = state.status || (await requestJSON("/api/status"));
  const dirty = Boolean(status.dirty);
  let message = `Hard reset to ${sha}?`;
  if (dirty) {
    message = "Uncommitted changes detected. A gitops-stash branch will be created, all changes will be committed, then a hard reset will run. Continue?";
  }
  if (!window.confirm(message)) {
    return;
  }
  try {
    const payload = {
      sha,
      confirm_dirty: dirty,
      message: `GitOps stash before reset to ${sha}`,
    };
    const result = await requestJSON("/api/reset", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    if (result.stash_branch) {
      showToast(`Stashed changes on ${result.stash_branch} and reset.`);
    } else {
      showToast("Reset complete.");
    }
    await loadStatus();
    await loadCommits(state.selectedBranch);
  } catch (err) {
    showToast(err.message);
  }
}

async function loadConfig() {
  try {
    const data = await requestJSON("/api/config");
    const config = data.config || {};
    state.config = config;
    dom.configRemoteUrl.value = config.remote_url || "";
    dom.configRemoteBranch.value = config.remote_branch || "main";
    dom.configGitUserName.value = config.git_user_name || "";
    dom.configGitUserEmail.value = config.git_user_email || "";
    dom.configWebhookPath.value = config.webhook_path || "pull";
    dom.configPollInterval.value =
      config.poll_interval_minutes === null || config.poll_interval_minutes === undefined
        ? ""
        : String(config.poll_interval_minutes);
    dom.configNotifications.checked = Boolean(config.notification_enabled);
    dom.configWebhookEnabled.checked = Boolean(config.webhook_enabled);
    dom.configYamlModules.checked = Boolean(config.yaml_modules_enabled);
    dom.configTheme.value = config.ui_theme || "system";
    applyTheme(dom.configTheme.value);
  } catch (err) {
    dom.configStatus.textContent = err.message;
  }
}

async function saveConfig() {
  const pollValue = dom.configPollInterval.value.trim();
  const payload = {
    remote_url: dom.configRemoteUrl.value.trim(),
    remote_branch: dom.configRemoteBranch.value.trim() || "main",
    git_user_name: dom.configGitUserName.value.trim(),
    git_user_email: dom.configGitUserEmail.value.trim(),
    webhook_path: dom.configWebhookPath.value.trim() || "pull",
    poll_interval_minutes: pollValue === "" ? null : Number(pollValue),
    notification_enabled: dom.configNotifications.checked,
    webhook_enabled: dom.configWebhookEnabled.checked,
    yaml_modules_enabled: dom.configYamlModules.checked,
    ui_theme: dom.configTheme.value,
  };
  if (Number.isNaN(payload.poll_interval_minutes)) {
    dom.configStatus.textContent = "Poll interval must be a number or blank.";
    return;
  }
  try {
    const data = await requestJSON("/api/config", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    if (data.status) {
      dom.configStatus.textContent = data.requires_restart
        ? "Saved. Restart the add-on to apply backend changes."
        : "Saved.";
    } else {
      dom.configStatus.textContent = "Save failed.";
    }
    applyTheme(payload.ui_theme);
    await loadStatus();
  } catch (err) {
    dom.configStatus.textContent = err.message;
  }
}

async function installCli() {
  if (!dom.cliInstallBtn) {
    return;
  }
  const overwrite = Boolean(dom.cliOverwrite && dom.cliOverwrite.checked);
  if (dom.cliStatus) {
    dom.cliStatus.textContent = "Installing CLI...";
  }
  try {
    const data = await requestJSON("/api/cli/install", {
      method: "POST",
      body: JSON.stringify({ overwrite }),
    });
    if (dom.cliStatus) {
      dom.cliStatus.textContent = `CLI installed in ${data.path}.`;
    }
    showToast("CLI installed");
    await loadStatus();
  } catch (err) {
    if (dom.cliStatus) {
      dom.cliStatus.textContent = err.message;
    }
    showToast(err.message);
  }
}

async function loadSshStatus() {
  try {
    const data = await requestJSON("/api/ssh/status");
    dom.sshStatus.textContent = data.private_key_exists
      ? "SSH keypair exists."
      : "No SSH keypair yet.";
    dom.sshGenerateBtn.disabled = data.private_key_exists || !data.ssh_dir_writable;
    dom.sshLoadBtn.disabled = !data.public_key_exists;
    dom.sshTestBtn.disabled = !data.private_key_exists || !data.ssh_available;
    dom.sshInstructions.textContent = data.private_key_exists
      ? "Add the public key to your Git provider."
      : "Generate a keypair, then add the public key to your Git provider.";
    dom.sshTestStatus.textContent = data.ssh_available
      ? "Test the SSH connection to GitHub once the key is added."
      : "SSH client is not available in the add-on image.";
  } catch (err) {
    dom.sshStatus.textContent = err.message;
  }
}

async function generateSshKey() {
  try {
    await requestJSON("/api/ssh/generate", { method: "POST" });
    showToast("SSH key generated");
    await loadSshStatus();
  } catch (err) {
    showToast(err.message);
  }
}

async function loadPublicKey() {
  try {
    const data = await requestJSON("/api/ssh/public_key");
    dom.sshPublicKey.textContent = data.public_key || "";
  } catch (err) {
    showToast(err.message);
  }
}

async function testSshKey() {
  dom.sshTestStatus.textContent = "Testing SSH connection to GitHub...";
  try {
    const data = await requestJSON("/api/ssh/test", {
      method: "POST",
      body: JSON.stringify({ host: "git@github.com" }),
    });
    const output = data.output ? data.output.trim().replace(/\s+/g, " ") : "";
    const message =
      data.message ||
      (data.status === "success" ? "SSH authentication succeeded." : "SSH authentication failed.");
    dom.sshTestStatus.textContent = output ? `${message} ${output}` : message;
    showToast(message);
  } catch (err) {
    dom.sshTestStatus.textContent = err.message;
    showToast(err.message);
  }
}

function loadMonaco() {
  if (window.monaco) {
    return Promise.resolve(window.monaco);
  }
  if (!window.require) {
    return Promise.reject(new Error("Editor loader is unavailable."));
  }
  if (!moduleEditorPromise) {
    moduleEditorPromise = new Promise((resolve, reject) => {
      window.require.config({ paths: { vs: `${MONACO_BASE}/vs` } });
      window.require(
        ["vs/editor/editor.main"],
        () => resolve(window.monaco),
        (err) => reject(err)
      );
    });
  }
  return moduleEditorPromise;
}

function createFallbackEditor() {
  dom.moduleEditor.innerHTML = "";
  const textarea = document.createElement("textarea");
  textarea.className = "module-editor-textarea";
  textarea.disabled = true;
  textarea.placeholder = "Select a module file to start editing.";
  textarea.addEventListener("input", () => {
    if (moduleEditorSetting) {
      return;
    }
    handleModuleEditorChange();
  });
  dom.moduleEditor.append(textarea);
  moduleEditorTextarea = textarea;
}

function ensureModuleEditor() {
  if (moduleEditor || moduleEditorTextarea || !dom.moduleEditor) {
    return Promise.resolve();
  }
  return loadMonaco()
    .then(() => {
      dom.moduleEditor.innerHTML = "";
      moduleEditor = window.monaco.editor.create(dom.moduleEditor, {
        value: "",
        language: "yaml",
        theme: getEditorTheme(),
        readOnly: true,
        automaticLayout: true,
        minimap: { enabled: false },
        scrollBeyondLastLine: false,
      });
      moduleEditor.onDidChangeModelContent(() => {
        if (moduleEditorSetting) {
          return;
        }
        handleModuleEditorChange();
      });
      dom.moduleEditorStatus.textContent = "";
    })
    .catch(() => {
      createFallbackEditor();
      dom.moduleEditorStatus.textContent =
        "Editor failed to load. Using the basic text editor.";
    });
}

function getModuleEditorValue() {
  if (moduleEditor) {
    return moduleEditor.getValue();
  }
  if (moduleEditorTextarea) {
    return moduleEditorTextarea.value;
  }
  return "";
}

function setModuleEditorReadOnly(readOnly) {
  if (moduleEditor) {
    moduleEditor.updateOptions({ readOnly });
  }
  if (moduleEditorTextarea) {
    moduleEditorTextarea.disabled = readOnly;
  }
}

function setModuleEditorContent(content, markClean = true) {
  const nextValue = content || "";
  moduleEditorSetting = true;
  if (moduleEditor) {
    moduleEditor.setValue(nextValue);
    requestAnimationFrame(() => moduleEditor && moduleEditor.layout());
  } else if (moduleEditorTextarea) {
    moduleEditorTextarea.value = nextValue;
  } else if (dom.moduleEditor) {
    dom.moduleEditor.innerHTML = `<div class="module-editor-placeholder">${nextValue
      ? "Loading editor..."
      : "Select a module file to start editing."}</div>`;
  }
  moduleEditorSetting = false;
  if (markClean) {
    state.moduleFileContent = nextValue;
    setModuleDirty(false);
  }
}

function handleModuleEditorChange() {
  const current = getModuleEditorValue();
  setModuleDirty(current !== state.moduleFileContent);
}

function updateModuleFileMeta() {
  if (!dom.moduleFileMeta) {
    return;
  }
  if (!state.selectedModuleFile) {
    dom.moduleFileMeta.textContent = "Select a module file to inspect and edit.";
    return;
  }
  const status = state.moduleFileDirty ? "Unsaved changes." : "Ready.";
  dom.moduleFileMeta.textContent = `${state.selectedModuleFile} - ${status}`;
}

function setModuleDirty(isDirty) {
  state.moduleFileDirty = isDirty;
  dom.moduleSaveBtn.disabled = !state.selectedModuleFile || !isDirty;
  updateModuleFileMeta();
  if (!isDirty && state.modulesStale && isModulesTabActive()) {
    state.modulesStale = false;
    loadModulesIndex();
  }
}

function clearModuleSelection() {
  state.selectedModuleFile = null;
  state.moduleFileContent = "";
  state.moduleFileDirty = false;
  state.moduleFileKind = null;
  state.moduleItemsByFile = {};
  state.moduleItemSelections = {};
  state.moduleItemOrder = {};
  state.lastModuleSelection = null;
  dom.moduleSaveBtn.disabled = true;
  dom.moduleDeleteBtn.disabled = true;
  dom.moduleEditorStatus.textContent = "";
  updateModuleFileMeta();
  updateModuleSelectionCount();
  updateModuleActionButtons();
  if (moduleEditor || moduleEditorTextarea) {
    setModuleEditorContent("", true);
    setModuleEditorReadOnly(true);
  } else if (dom.moduleEditor) {
    dom.moduleEditor.innerHTML =
      "<div class=\"module-editor-placeholder\">Select a module file to start editing.</div>";
  }
}

function confirmDiscardModuleChanges() {
  if (!state.moduleFileDirty) {
    return true;
  }
  const target = state.selectedModuleFile || "this file";
  return window.confirm(`Discard unsaved changes to ${target}?`);
}

function updateModuleSelectionCount() {
  if (!dom.moduleSelectionCount) {
    return;
  }
  const selected = Object.values(state.moduleItemSelections).filter(Boolean).length;
  if (!selected) {
    dom.moduleSelectionCount.textContent = "No items selected.";
    updateModuleActionButtons();
    return;
  }
  dom.moduleSelectionCount.textContent = `${selected} item${selected === 1 ? "" : "s"} selected.`;
  updateModuleActionButtons();
}

function moduleItemKey(item) {
  return JSON.stringify(item.selector || {});
}

function withItemPath(item, filePath) {
  if (!item || item.path === filePath) {
    return item;
  }
  return { ...item, path: filePath };
}

function setSelectedItems(items, filePath) {
  state.moduleItemSelections = {};
  items.forEach((item) => {
    const stored = withItemPath(item, filePath);
    state.moduleItemSelections[moduleItemKey(stored)] = stored;
  });
  state.lastModuleSelection = {
    filePath,
    key: items.length ? moduleItemKey(items[items.length - 1]) : null,
  };
  updateModuleSelectionCount();
}

function toggleSelectedItem(item, filePath) {
  const key = moduleItemKey(item);
  if (state.moduleItemSelections[key]) {
    delete state.moduleItemSelections[key];
  } else {
    state.moduleItemSelections[key] = withItemPath(item, filePath);
  }
  state.lastModuleSelection = { filePath, key };
  updateModuleSelectionCount();
}

function selectRange(filePath, items, targetKey) {
  const order = state.moduleItemOrder[filePath] || [];
  if (!order.length) {
    return;
  }
  const startKey =
    state.lastModuleSelection && state.lastModuleSelection.filePath === filePath
      ? state.lastModuleSelection.key
      : null;
  if (!startKey) {
    return;
  }
  const startIndex = order.indexOf(startKey);
  const endIndex = order.indexOf(targetKey);
  if (startIndex < 0 || endIndex < 0) {
    return;
  }
  const itemsByKey = items.reduce((acc, item) => {
    acc[moduleItemKey(item)] = item;
    return acc;
  }, {});
  const [from, to] = startIndex < endIndex ? [startIndex, endIndex] : [endIndex, startIndex];
  const selection = order.slice(from, to + 1).map((key) => itemsByKey[key]).filter(Boolean);
  setSelectedItems(selection, filePath);
}

function updateModuleActionButtons() {
  if (!dom.moduleMoveBtn || !dom.moduleUnassignBtn || !dom.moduleDeleteItemsBtn) {
    return;
  }
  const hasSelection = Object.values(state.moduleItemSelections).some(Boolean);
  const enabled = state.modulesEnabled && hasSelection && state.selectedModuleFile;
  dom.moduleMoveBtn.disabled = !enabled;
  dom.moduleUnassignBtn.disabled = !enabled;
  dom.moduleDeleteItemsBtn.disabled = !enabled;
}

function getOrderedSelectedItems(filePath) {
  const order = state.moduleItemOrder[filePath] || [];
  const selections = state.moduleItemSelections;
  const ordered = order.map((key) => selections[key]).filter(Boolean);
  if (ordered.length) {
    return ordered;
  }
  return Object.values(selections).filter(Boolean);
}

function buildOperatePayload() {
  const filePath = state.selectedModuleFile;
  const selections = getOrderedSelectedItems(filePath);
  return selections.map((item) => ({
    path: item.path || filePath,
    selector: item.selector,
  }));
}

function getModuleById(moduleId) {
  return state.modulesIndex.find((module) => module.id === moduleId);
}

function renderModuleSelect(modules) {
  dom.moduleSelect.innerHTML = "";
  if (!modules.length) {
    dom.moduleSelect.disabled = true;
    const option = document.createElement("option");
    option.textContent = "No modules found";
    dom.moduleSelect.append(option);
    return;
  }
  dom.moduleSelect.disabled = false;
  const nameCounts = modules.reduce((acc, module) => {
    acc[module.name] = (acc[module.name] || 0) + 1;
    return acc;
  }, {});

  const packages = modules.filter((module) => module.kind === "package");
  const oneOffs = modules.filter((module) => module.kind === "one_offs");
  const unassigned = modules.filter((module) => module.kind === "unassigned");

  const kindLabel = (kind) => {
    if (kind === "one_offs") {
      return "one-offs";
    }
    return kind || "module";
  };

  const appendGroup = (label, items) => {
    if (!items.length) {
      return;
    }
    const group = document.createElement("optgroup");
    group.label = label;
    items.forEach((module) => {
      const option = document.createElement("option");
      option.value = module.id;
      const suffix = nameCounts[module.name] > 1 ? ` (${kindLabel(module.kind)})` : "";
      option.textContent = `${module.name}${suffix}`;
      group.append(option);
    });
    dom.moduleSelect.append(group);
  };

  appendGroup("Packages", packages);
  appendGroup("One-offs", oneOffs);
  appendGroup("Unassigned", unassigned);
}

function renderModuleFileList(module) {
  dom.moduleFileList.innerHTML = "";
  if (!module || !module.files || !module.files.length) {
    dom.moduleFileList.innerHTML =
      "<div class=\"diff-placeholder\">No module files found.</div>";
    return;
  }
  module.files.forEach((filePath) => {
    const item = document.createElement("div");
    item.className = "commit-item";
    if (state.selectedModuleFile === filePath) {
      item.classList.add("is-active");
    }
    const title = document.createElement("div");
    title.textContent = filePath;
    item.append(title);
    item.addEventListener("click", async () => {
      const loaded = await selectModuleFile(filePath);
      if (loaded) {
        renderModuleFileList(module);
      }
    });
    dom.moduleFileList.append(item);

    if (state.selectedModuleFile === filePath && state.moduleItemsByFile[filePath]) {
      const items = state.moduleItemsByFile[filePath];
      const list = document.createElement("div");
      list.className = "module-item-list";
      items.forEach((entry) => {
        const key = moduleItemKey(entry);
        const card = document.createElement("div");
        card.className = "module-item";
        if (state.moduleItemSelections[key]) {
          card.classList.add("is-active");
        }
        const titleLine = document.createElement("div");
        titleLine.className = "module-item-title";
        titleLine.textContent = entry.name || entry.id || "Untitled item";
        const metaLine = document.createElement("div");
        metaLine.className = "module-item-meta";
        metaLine.textContent = entry.id || entry.helper_type || "Item";
        card.append(titleLine, metaLine);
        card.addEventListener("click", async (event) => {
          event.preventDefault();
          event.stopPropagation();
          if (!confirmDiscardModuleChanges()) {
            return;
          }
          const isMulti = event.shiftKey || event.metaKey || event.ctrlKey;
          if (event.shiftKey) {
            selectRange(filePath, state.moduleItemsByFile[filePath], key);
          } else if (event.metaKey || event.ctrlKey) {
            toggleSelectedItem(entry, filePath);
          } else {
            setSelectedItems([entry], filePath);
          }
          renderModuleFileList(module);
          await loadModuleSelection(filePath, isMulti);
        });
        list.append(card);
      });
      item.append(list);
    }
  });
}

async function loadModulesIndex(options = {}) {
  const allowDirty = options.allowDirty !== false;
  if (!dom.moduleSelect || !dom.moduleFileList) {
    return;
  }
  if (!allowDirty && state.moduleFileDirty) {
    state.modulesStale = true;
    return;
  }
  if (moduleIndexLoading) {
    return;
  }
  moduleIndexLoading = true;
  dom.moduleFileList.innerHTML =
    "<div class=\"diff-placeholder\">Loading module files...</div>";
  dom.moduleSelect.disabled = true;
  try {
    const data = await requestJSON("/api/modules/index");
    state.modulesIndex = data.modules || [];
    state.modulesStale = false;
    renderModuleSelect(state.modulesIndex);
    if (!state.modulesIndex.length) {
      dom.moduleFileList.innerHTML =
        "<div class=\"diff-placeholder\">No YAML module files found.</div>";
      state.selectedModuleId = null;
      clearModuleSelection();
      return;
    }
    if (!state.selectedModuleId || !getModuleById(state.selectedModuleId)) {
      state.selectedModuleId = state.modulesIndex[0].id;
    }
    dom.moduleSelect.value = state.selectedModuleId;
    const activeModule = getModuleById(state.selectedModuleId);
    if (
      state.selectedModuleFile &&
      (!activeModule || !activeModule.files.includes(state.selectedModuleFile))
    ) {
      clearModuleSelection();
    }
    renderModuleFileList(activeModule);
  } catch (err) {
    state.modulesIndex = [];
    state.selectedModuleId = null;
    dom.moduleSelect.innerHTML = "";
    dom.moduleSelect.disabled = true;
    dom.moduleFileList.innerHTML = `<div class="diff-placeholder">${err.message}</div>`;
    clearModuleSelection();
  } finally {
    moduleIndexLoading = false;
  }
}

async function loadModuleItems(filePath) {
  try {
    const data = await requestJSON(`/api/modules/items?path=${encodeURIComponent(filePath)}`);
    const items = data.items || [];
    state.moduleItemsByFile[filePath] = items;
    state.moduleItemOrder[filePath] = items.map((item) => moduleItemKey(item));
    state.moduleFileKind = data.file_kind || null;
  } catch (err) {
    dom.moduleEditorStatus.textContent = err.message;
    state.moduleItemsByFile[filePath] = [];
    state.moduleItemOrder[filePath] = [];
  }
}

async function loadModuleSelection(filePath, isMulti) {
  const selections = Object.values(state.moduleItemSelections);
  if (!selections.length) {
    return;
  }
  if (isMulti && selections.length > 1) {
    const snippets = [];
    const orderedSelections = (state.moduleItemOrder[filePath] || [])
      .map((key) => state.moduleItemSelections[key])
      .filter(Boolean);
    for (const item of orderedSelections) {
      const selector = encodeURIComponent(JSON.stringify(item.selector));
      const data = await requestJSON(
        `/api/modules/item?path=${encodeURIComponent(filePath)}&selector=${selector}`
      );
      snippets.push(`# --- ITEM: ${item.id || "item"} ---\n${data.yaml || ""}`.trim());
    }
    setModuleEditorReadOnly(true);
    setModuleEditorContent(snippets.join("\n\n"), true);
    dom.moduleEditorStatus.textContent =
      "Multiple items selected. Use move, unassign, or delete actions to operate on this set.";
    return;
  }
  const item = selections[0];
  const selector = encodeURIComponent(JSON.stringify(item.selector));
  const data = await requestJSON(
    `/api/modules/item?path=${encodeURIComponent(filePath)}&selector=${selector}`
  );
  setModuleEditorReadOnly(false);
  setModuleEditorContent(data.yaml || "", true);
  dom.moduleEditorStatus.textContent = "";
}

async function selectModuleFile(filePath, options = {}) {
  const force = options.force === true;
  const confirmDiscard = options.confirmDiscard !== false;
  if (!force && state.selectedModuleFile === filePath) {
    return true;
  }
  if (confirmDiscard && !confirmDiscardModuleChanges()) {
    return false;
  }
  state.selectedModuleFile = filePath;
  dom.moduleFileMeta.textContent = `Loading ${filePath}...`;
  dom.moduleDeleteBtn.disabled = true;
  dom.moduleSaveBtn.disabled = true;
  dom.moduleEditorStatus.textContent = "";
  state.moduleItemSelections = {};
  state.moduleItemOrder[filePath] = [];
  state.lastModuleSelection = null;
  try {
    const data = await requestJSON(
      `/api/modules/file?path=${encodeURIComponent(filePath)}`
    );
    await ensureModuleEditor();
    setModuleEditorReadOnly(false);
    setModuleEditorContent(data.content || "", true);
    state.selectedModuleFile = data.path || filePath;
    await loadModuleItems(state.selectedModuleFile);
    updateModuleSelectionCount();
    dom.moduleDeleteBtn.disabled = false;
    updateModuleFileMeta();
    return true;
  } catch (err) {
    dom.moduleEditorStatus.textContent = err.message;
    showToast(err.message);
    clearModuleSelection();
    return false;
  }
}

async function saveModuleFile() {
  if (!state.selectedModuleFile) {
    return;
  }
  const selections = Object.values(state.moduleItemSelections);
  if (selections.length === 1) {
    await saveModuleItem(selections[0]);
    return;
  }
  if (selections.length > 1) {
    showToast("Save is available for single-item edits only.");
    return;
  }
  const content = getModuleEditorValue();
  dom.moduleSaveBtn.disabled = true;
  dom.moduleEditorStatus.textContent = "Saving module file...";
  try {
    await requestJSON("/api/modules/file", {
      method: "POST",
      body: JSON.stringify({ path: state.selectedModuleFile, content }),
    });
    state.moduleFileContent = content;
    setModuleDirty(false);
    dom.moduleEditorStatus.textContent = "Module file saved.";
    showToast("Module file saved");
    await loadStatus();
  } catch (err) {
    dom.moduleEditorStatus.textContent = err.message;
    showToast(err.message);
  }
}

async function saveModuleItem(item) {
  const content = getModuleEditorValue();
  dom.moduleSaveBtn.disabled = true;
  dom.moduleEditorStatus.textContent = "Saving module item...";
  try {
    await requestJSON("/api/modules/item", {
      method: "POST",
      body: JSON.stringify({
        path: state.selectedModuleFile,
        selector: item.selector,
        yaml: content,
      }),
    });
    state.moduleFileContent = content;
    setModuleDirty(false);
    dom.moduleEditorStatus.textContent = "Module item saved.";
    showToast("Module item saved");
    await loadModuleItems(state.selectedModuleFile);
    state.moduleItemSelections = {};
    state.lastModuleSelection = null;
    updateModuleSelectionCount();
    renderModuleFileList(getModuleById(state.selectedModuleId));
    await loadStatus();
  } catch (err) {
    dom.moduleEditorStatus.textContent = err.message;
    showToast(err.message);
  }
}

async function deleteModuleFile() {
  if (!state.selectedModuleFile) {
    return;
  }
  const warning = state.moduleFileDirty
    ? "Unsaved changes will be lost."
    : "This cannot be undone.";
  if (!window.confirm(`Delete ${state.selectedModuleFile}? ${warning}`)) {
    return;
  }
  dom.moduleDeleteBtn.disabled = true;
  dom.moduleEditorStatus.textContent = "Deleting module file...";
  try {
    await requestJSON(
      `/api/modules/file?path=${encodeURIComponent(state.selectedModuleFile)}`,
      { method: "DELETE" }
    );
    showToast("Module file deleted");
    clearModuleSelection();
    await loadStatus();
    await loadModulesIndex();
  } catch (err) {
    dom.moduleEditorStatus.textContent = err.message;
    showToast(err.message);
  }
}

function setExportTab(tab) {
  state.exportTab = tab;
  qsa(".export-tab-btn").forEach((btn) => {
    btn.classList.toggle("is-active", btn.dataset.exportTab === tab);
  });
  if (dom.exportConfigEntities && dom.exportConfigOther) {
    const isEntities = tab === "entities";
    dom.exportConfigEntities.hidden = !isEntities;
    dom.exportConfigOther.hidden = isEntities;
  }
  if (dom.exportRunBtn) {
    const label = tab.charAt(0).toUpperCase() + tab.slice(1);
    dom.exportRunBtn.textContent = `Run ${label} export`;
  }
  loadExportFile(tab);
}

async function loadExportConfig() {
  if (!dom.exportBlacklist) {
    return;
  }
  try {
    const data = await requestJSON("/api/exports/config");
    state.exportConfig = data.config || null;
    const blacklist =
      (state.exportConfig &&
        state.exportConfig.entities &&
        state.exportConfig.entities.integration_blacklist) ||
      [];
    dom.exportBlacklist.value = blacklist.join("\n");
  } catch (err) {
    if (dom.exportStatus) {
      dom.exportStatus.textContent = err.message;
    }
  }
}

function parseBlacklistInput(raw) {
  if (!raw) {
    return [];
  }
  return raw
    .split(/[\n,]+/)
    .map((entry) => entry.trim())
    .filter((entry) => entry);
}

async function saveExportConfig() {
  if (!dom.exportBlacklist) {
    return;
  }
  const blacklist = parseBlacklistInput(dom.exportBlacklist.value);
  if (dom.exportStatus) {
    dom.exportStatus.textContent = "Saving export config...";
  }
  try {
    const data = await requestJSON("/api/exports/config", {
      method: "POST",
      body: JSON.stringify({
        schema_version: 1,
        entities: { integration_blacklist: blacklist },
      }),
    });
    state.exportConfig = data.config || null;
    dom.exportBlacklist.value = blacklist.join("\n");
    if (dom.exportStatus) {
      dom.exportStatus.textContent = "Export config saved.";
    }
    showToast("Export config saved");
  } catch (err) {
    if (dom.exportStatus) {
      dom.exportStatus.textContent = err.message;
    }
    showToast(err.message);
  }
}

async function runExport() {
  const tab = state.exportTab;
  if (dom.exportStatus) {
    dom.exportStatus.textContent = `Running ${tab} export...`;
  }
  try {
    const data = await requestJSON(`/api/exports/run/${encodeURIComponent(tab)}`, {
      method: "POST",
    });
    if (dom.exportStatus) {
      dom.exportStatus.textContent = `Export complete (${data.rows || 0} rows).`;
    }
    await loadExportFile(tab);
    showToast("Export complete");
    await loadStatus();
  } catch (err) {
    if (dom.exportStatus) {
      dom.exportStatus.textContent = err.message;
    }
    showToast(err.message);
  }
}

function parseCsv(content) {
  const rows = [];
  let row = [];
  let cell = "";
  let inQuotes = false;
  for (let i = 0; i < content.length; i += 1) {
    const char = content[i];
    if (inQuotes) {
      if (char === "\"") {
        const nextChar = content[i + 1];
        if (nextChar === "\"") {
          cell += "\"";
          i += 1;
        } else {
          inQuotes = false;
        }
      } else {
        cell += char;
      }
      continue;
    }
    if (char === "\"") {
      inQuotes = true;
      continue;
    }
    if (char === ",") {
      row.push(cell);
      cell = "";
      continue;
    }
    if (char === "\n") {
      row.push(cell);
      rows.push(row);
      row = [];
      cell = "";
      continue;
    }
    if (char === "\r") {
      continue;
    }
    cell += char;
  }
  if (cell.length || row.length) {
    row.push(cell);
    rows.push(row);
  }
  return rows;
}

function renderExportTable(content) {
  if (!dom.exportTable) {
    return;
  }
  dom.exportTable.innerHTML = "";
  if (!content || !content.trim()) {
    dom.exportTable.innerHTML =
      "<div class=\"export-table-placeholder\">No export run yet.</div>";
    return;
  }
  const rows = parseCsv(content);
  if (!rows.length) {
    dom.exportTable.innerHTML =
      "<div class=\"export-table-placeholder\">No export run yet.</div>";
    return;
  }
  const table = document.createElement("table");
  const thead = document.createElement("thead");
  const headerRow = document.createElement("tr");
  rows[0].forEach((cell) => {
    const th = document.createElement("th");
    th.textContent = cell;
    headerRow.append(th);
  });
  thead.append(headerRow);
  table.append(thead);

  const tbody = document.createElement("tbody");
  rows.slice(1).forEach((row) => {
    const tr = document.createElement("tr");
    rows[0].forEach((_header, index) => {
      const td = document.createElement("td");
      td.textContent = row[index] || "";
      tr.append(td);
    });
    tbody.append(tr);
  });
  table.append(tbody);
  dom.exportTable.append(table);
}

async function loadExportFile(tab) {
  if (!dom.exportTable) {
    return;
  }
  if (dom.exportFileMeta) {
    dom.exportFileMeta.textContent = "Loading export file...";
  }
  try {
    const data = await requestJSON(`/api/exports/file/${encodeURIComponent(tab)}`);
    renderExportTable(data.content || "");
    if (dom.exportFileMeta) {
      dom.exportFileMeta.textContent = data.path || "";
    }
  } catch (err) {
    if (dom.exportFileMeta) {
      dom.exportFileMeta.textContent = "No export run yet.";
    }
    if (err.message && err.message.toLowerCase().includes("not found")) {
      renderExportTable("");
      return;
    }
    dom.exportTable.innerHTML = `<div class=\"export-table-placeholder\">${err.message}</div>`;
  }
}

function parseGroupMembers(raw) {
  if (!raw) {
    return [];
  }
  return raw
    .split("\n")
    .map((entry) => entry.trim())
    .filter((entry) => entry);
}

function groupDestinationPayload() {
  if (!dom.groupsDestinationType) {
    return null;
  }
  const type = dom.groupsDestinationType.value;
  if (type === "package") {
    return {
      type,
      package_name: (dom.groupsPackageName && dom.groupsPackageName.value.trim()) || "",
    };
  }
  if (type === "one_off") {
    return {
      type,
      filename: (dom.groupsOneOffFilename && dom.groupsOneOffFilename.value.trim()) || "",
    };
  }
  return null;
}

function setGroupsEditorSelection(objectId) {
  state.selectedGroupObjectId = objectId || null;
  const selected = state.groupsData
    ? (state.groupsData.managed || []).find((row) => row.object_id === objectId)
    : null;
  if (!selected) {
    if (dom.groupsObjectId) {
      dom.groupsObjectId.value = "";
      dom.groupsObjectId.disabled = false;
    }
    if (dom.groupsName) {
      dom.groupsName.value = "";
    }
    if (dom.groupsMembers) {
      dom.groupsMembers.value = "";
    }
    if (dom.groupsDelete) {
      dom.groupsDelete.disabled = true;
    }
    if (dom.groupsDestinationType) {
      dom.groupsDestinationType.disabled = false;
    }
    if (dom.groupsPackageName) {
      dom.groupsPackageName.disabled = false;
    }
    if (dom.groupsOneOffFilename) {
      dom.groupsOneOffFilename.disabled = false;
    }
    return;
  }

  if (dom.groupsObjectId) {
    dom.groupsObjectId.value = selected.object_id || "";
    dom.groupsObjectId.disabled = true;
  }
  if (dom.groupsName) {
    dom.groupsName.value = selected.name || "";
  }
  if (dom.groupsMembers) {
    dom.groupsMembers.value = (selected.members || []).join("\n");
  }
  if (dom.groupsDelete) {
    dom.groupsDelete.disabled = false;
  }
  if (dom.groupsDestinationType) {
    dom.groupsDestinationType.disabled = true;
  }
  if (dom.groupsPackageName) {
    dom.groupsPackageName.disabled = true;
  }
  if (dom.groupsOneOffFilename) {
    dom.groupsOneOffFilename.disabled = true;
  }
}

function updateGroupsDestinationFields() {
  if (!dom.groupsDestinationType) {
    return;
  }
  const type = dom.groupsDestinationType.value;
  if (dom.groupsDestinationPackage) {
    dom.groupsDestinationPackage.hidden = type !== "package";
  }
  if (dom.groupsDestinationOneOff) {
    dom.groupsDestinationOneOff.hidden = type !== "one_off";
  }
}

function renderGroupsRestartBanner(restart) {
  if (!dom.groupsRestartBanner) {
    return;
  }
  const needed = restart && restart.restart_needed;
  dom.groupsRestartBanner.hidden = !needed;
}

function renderGroupsConfigWarning(configuration) {
  if (!dom.groupsConfigWarning) {
    return;
  }
  const warning = configuration && configuration.warning;
  if (!warning) {
    dom.groupsConfigWarning.hidden = true;
    dom.groupsConfigWarning.textContent = "";
    return;
  }
  dom.groupsConfigWarning.hidden = false;
  dom.groupsConfigWarning.textContent = warning;
}

function renderGroupsTable(container, rows, options) {
  if (!container) {
    return;
  }
  container.innerHTML = "";
  if (!rows || !rows.length) {
    const placeholder = document.createElement("div");
    placeholder.className = "export-table-placeholder";
    placeholder.textContent = options && options.emptyText ? options.emptyText : "No entries.";
    container.append(placeholder);
    return;
  }

  const table = document.createElement("table");
  const thead = document.createElement("thead");
  const headerRow = document.createElement("tr");
  const columns = (options && options.columns) || [];
  columns.forEach((column) => {
    const th = document.createElement("th");
    th.textContent = column.label;
    headerRow.append(th);
  });
  thead.append(headerRow);
  table.append(thead);

  const tbody = document.createElement("tbody");
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    columns.forEach((column) => {
      const td = document.createElement("td");
      if (column.render) {
        column.render(td, row);
      } else {
        td.textContent = row[column.key] || "";
      }
      tr.append(td);
    });
    tbody.append(tr);
  });
  table.append(tbody);
  container.append(table);
}

function applyGroupsFilters(rows) {
  if (!rows) {
    return [];
  }
  const showIgnored = dom.groupsShowIgnored ? dom.groupsShowIgnored.checked : false;
  if (showIgnored) {
    return rows;
  }
  return rows.filter((row) => !row.ignored);
}

async function setGroupIgnored(entityId, ignored) {
  if (!dom.groupsStatus) {
    return;
  }
  dom.groupsStatus.textContent = ignored ? "Ignoring group..." : "Removing ignore...";
  try {
    await requestJSON("/api/groups/ignore", {
      method: "POST",
      body: JSON.stringify({ entity_id: entityId, ignored }),
    });
    await loadGroupsData();
    showToast(ignored ? "Group ignored" : "Group unignored");
  } catch (err) {
    dom.groupsStatus.textContent = err.message;
    showToast(err.message);
  }
}

async function importGroup(entityId) {
  if (!dom.groupsStatus) {
    return;
  }
  dom.groupsStatus.textContent = `Importing ${entityId}...`;
  try {
    await requestJSON("/api/groups/import", {
      method: "POST",
      body: JSON.stringify({ entity_id: entityId, destination: groupDestinationPayload() }),
    });
    await loadGroupsData();
    showToast("Group imported");
    await loadStatus();
  } catch (err) {
    dom.groupsStatus.textContent = err.message;
    showToast(err.message);
  }
}

async function saveGroup() {
  if (!dom.groupsStatus || !dom.groupsObjectId || !dom.groupsName) {
    return;
  }
  const payload = {
    object_id: dom.groupsObjectId.value,
    name: dom.groupsName.value,
    members: parseGroupMembers(dom.groupsMembers ? dom.groupsMembers.value : ""),
    destination: groupDestinationPayload(),
  };
  dom.groupsStatus.textContent = "Saving group...";
  try {
    const data = await requestJSON("/api/groups", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    const warnings =
      (data.sync && data.sync.warnings && data.sync.warnings.length)
        ? ` Warnings: ${data.sync.warnings.join(" | ")}`
        : "";
    dom.groupsStatus.textContent = `Saved group.${data.object_id || ""}.${warnings}`;
    await loadGroupsData();
    setGroupsEditorSelection(data.object_id);
    showToast("Group saved");
    await loadStatus();
  } catch (err) {
    dom.groupsStatus.textContent = err.message;
    showToast(err.message);
  }
}

async function deleteGroup() {
  if (!dom.groupsStatus || !state.selectedGroupObjectId) {
    return;
  }
  const objectId = state.selectedGroupObjectId;
  dom.groupsStatus.textContent = `Deleting group.${objectId}...`;
  try {
    await requestJSON(`/api/groups/${encodeURIComponent(objectId)}`, { method: "DELETE" });
    await loadGroupsData();
    setGroupsEditorSelection(null);
    showToast("Group deleted");
    await loadStatus();
  } catch (err) {
    dom.groupsStatus.textContent = err.message;
    showToast(err.message);
  }
}

async function ackGroupsRestart() {
  if (!dom.groupsStatus) {
    return;
  }
  dom.groupsStatus.textContent = "Acknowledging restart...";
  try {
    await requestJSON("/api/groups/restart_ack", { method: "POST" });
    await loadGroupsData();
    showToast("Restart acknowledged");
  } catch (err) {
    dom.groupsStatus.textContent = err.message;
    showToast(err.message);
  }
}

function renderGroups() {
  const data = state.groupsData || {};
  renderGroupsRestartBanner(data.restart || null);
  renderGroupsConfigWarning(data.configuration || null);

  const managedRows = applyGroupsFilters(data.managed || []);
  const unmanagedRows = applyGroupsFilters(data.unmanaged || []);

  renderGroupsTable(dom.groupsManagedTable, managedRows, {
    emptyText: "No managed groups found.",
    columns: [
      { key: "entity_id", label: "Entity ID" },
      { key: "name", label: "Name" },
      {
        key: "member_count",
        label: "Members",
        render: (cell, row) => {
          cell.textContent = String(row.member_count || 0);
        },
      },
      {
        key: "source",
        label: "Source",
        render: (cell, row) => {
          cell.textContent = row.source || "";
        },
      },
      {
        key: "actions",
        label: "Actions",
        render: (cell, row) => {
          const editBtn = document.createElement("button");
          editBtn.className = "btn";
          editBtn.textContent = "Edit";
          editBtn.addEventListener("click", () => setGroupsEditorSelection(row.object_id));

          const ignoreBtn = document.createElement("button");
          ignoreBtn.className = "btn";
          ignoreBtn.textContent = row.ignored ? "Unignore" : "Ignore";
          ignoreBtn.addEventListener("click", () => setGroupIgnored(row.entity_id, !row.ignored));

          cell.append(editBtn, ignoreBtn);
        },
      },
    ],
  });

  const showUnmanaged = dom.groupsShowUnmanaged ? dom.groupsShowUnmanaged.checked : false;
  if (dom.groupsUnmanagedSection) {
    dom.groupsUnmanagedSection.hidden = !showUnmanaged;
  }
  if (showUnmanaged) {
    renderGroupsTable(dom.groupsUnmanagedTable, unmanagedRows, {
      emptyText:
        "No unmanaged groups found (or Home Assistant API is unavailable).",
      columns: [
        { key: "entity_id", label: "Entity ID" },
        { key: "name", label: "Name" },
        {
          key: "member_count",
          label: "Members",
          render: (cell, row) => {
            cell.textContent = String(row.member_count || 0);
          },
        },
        {
          key: "actions",
          label: "Actions",
          render: (cell, row) => {
            const importBtn = document.createElement("button");
            importBtn.className = "btn btn-primary";
            importBtn.textContent = "Import";
            importBtn.addEventListener("click", () => importGroup(row.entity_id));

            const ignoreBtn = document.createElement("button");
            ignoreBtn.className = "btn";
            ignoreBtn.textContent = row.ignored ? "Unignore" : "Ignore";
            ignoreBtn.addEventListener("click", () => setGroupIgnored(row.entity_id, !row.ignored));

            cell.append(importBtn, ignoreBtn);
          },
        },
      ],
    });
  }

  if (state.selectedGroupObjectId) {
    setGroupsEditorSelection(state.selectedGroupObjectId);
  }
}

async function loadGroupsData() {
  if (!dom.groupsManagedTable) {
    return;
  }
  if (dom.groupsStatus) {
    dom.groupsStatus.textContent = "Loading groups...";
  }
  try {
    const data = await requestJSON("/api/groups");
    state.groupsData = data;
    if (dom.groupsStatus) {
      dom.groupsStatus.textContent = "";
    }
    renderGroups();
  } catch (err) {
    state.groupsData = null;
    if (dom.groupsStatus) {
      dom.groupsStatus.textContent = err.message;
    }
    renderGroups();
    showToast(err.message);
  }
}

function renderMovePackageOptions() {
  if (!dom.moduleMovePackage) {
    return [];
  }
  dom.moduleMovePackage.innerHTML = "";
  const packages = state.modulesIndex
    .filter((module) => module.kind === "package")
    .map((module) => module.name)
    .sort((a, b) => a.localeCompare(b));
  if (!packages.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "No packages found";
    dom.moduleMovePackage.append(option);
    dom.moduleMovePackage.disabled = true;
    return [];
  }
  dom.moduleMovePackage.disabled = false;
  packages.forEach((name) => {
    const option = document.createElement("option");
    option.value = name;
    option.textContent = name;
    dom.moduleMovePackage.append(option);
  });
  return packages;
}

function getMoveTargetType() {
  const selected = qs("input[name=\"module-move-type\"]:checked");
  return selected ? selected.value : "existing_package";
}

function setMoveTargetType(type) {
  qsa("input[name=\"module-move-type\"]").forEach((input) => {
    input.checked = input.value === type;
  });
  qsa(".module-move-field").forEach((field) => {
    field.hidden = field.dataset.field !== type;
  });
  updateMoveModalSummary();
  updateMoveModalConfirmState();
}

function updateMoveModalSummary() {
  if (!dom.moduleMoveSummary) {
    return;
  }
  const selections = Object.values(state.moduleItemSelections).filter(Boolean);
  if (!selections.length) {
    dom.moduleMoveSummary.textContent = "Select items to move.";
    return;
  }
  const count = selections.length;
  const sources = new Set(
    selections
      .map((item) => item.path || state.selectedModuleFile)
      .filter(Boolean)
  );
  const sourceLabel = sources.size ? Array.from(sources).join(", ") : "selected file";
  const targetType = getMoveTargetType();
  let targetLabel = "a destination";
  if (targetType === "existing_package") {
    const name = dom.moduleMovePackage ? dom.moduleMovePackage.value : "";
    targetLabel = name ? `package "${name}"` : "an existing package";
  } else if (targetType === "new_package") {
    const name = dom.moduleMoveNewPackage ? dom.moduleMoveNewPackage.value.trim() : "";
    targetLabel = name ? `new package "${name}"` : "a new package";
  } else if (targetType === "one_off") {
    const name = dom.moduleMoveOneOff ? dom.moduleMoveOneOff.value.trim() : "";
    targetLabel = name ? `one-off "${name}"` : "a one-off file";
  }
  dom.moduleMoveSummary.textContent =
    `Moving ${count} item${count === 1 ? "" : "s"} from ${sourceLabel} to ${targetLabel}.`;
}

function updateMoveModalConfirmState() {
  if (!dom.moduleMoveConfirm) {
    return;
  }
  const selections = Object.values(state.moduleItemSelections).filter(Boolean);
  let valid = selections.length > 0;
  const targetType = getMoveTargetType();
  if (targetType === "existing_package") {
    valid = valid && dom.moduleMovePackage && dom.moduleMovePackage.value;
  } else if (targetType === "new_package") {
    valid = valid && dom.moduleMoveNewPackage && dom.moduleMoveNewPackage.value.trim();
  } else if (targetType === "one_off") {
    valid = valid && dom.moduleMoveOneOff && dom.moduleMoveOneOff.value.trim();
  }
  dom.moduleMoveConfirm.disabled = !valid;
}

function openMoveModal() {
  if (!state.modulesEnabled) {
    showToast("YAML Modules sync is disabled.");
    return;
  }
  const selections = Object.values(state.moduleItemSelections).filter(Boolean);
  if (!selections.length) {
    showToast("Select items to move.");
    return;
  }
  if (!confirmDiscardModuleChanges()) {
    return;
  }
  const packages = renderMovePackageOptions();
  const existingInput = qs("input[name=\"module-move-type\"][value=\"existing_package\"]");
  if (existingInput) {
    existingInput.disabled = packages.length === 0;
  }
  const defaultType = packages.length ? "existing_package" : "new_package";
  setMoveTargetType(defaultType);
  if (dom.moduleMoveModal) {
    dom.moduleMoveModal.classList.add("is-visible");
    dom.moduleMoveModal.setAttribute("aria-hidden", "false");
  }
  updateMoveModalSummary();
  updateMoveModalConfirmState();
}

function closeMoveModal() {
  if (!dom.moduleMoveModal) {
    return;
  }
  dom.moduleMoveModal.classList.remove("is-visible");
  dom.moduleMoveModal.setAttribute("aria-hidden", "true");
}

async function operateModuleItems(operation, moveTarget) {
  const selectedFile = state.selectedModuleFile;
  const payloadItems = buildOperatePayload();
  if (!payloadItems.length) {
    showToast("Select items to operate on.");
    return false;
  }
  dom.moduleEditorStatus.textContent = `Running ${operation}...`;
  updateModuleActionButtons();
  if (dom.moduleMoveConfirm) {
    dom.moduleMoveConfirm.disabled = true;
  }
  try {
    const result = await requestJSON("/api/modules/items/operate", {
      method: "POST",
      body: JSON.stringify({
        operation,
        items: payloadItems,
        move_target: moveTarget,
      }),
    });
    const warnings = result.warnings || [];
    dom.moduleEditorStatus.textContent = warnings.length
      ? `Operation complete with warnings: ${warnings.join(" | ")}`
      : "Operation complete.";
    showToast(
      warnings.length ? "Operation complete with warnings" : "Operation complete"
    );
    state.moduleItemSelections = {};
    state.lastModuleSelection = null;
    updateModuleSelectionCount();
    setModuleDirty(false);
    await loadStatus();
    await loadModulesIndex();
    if (selectedFile) {
      await selectModuleFile(selectedFile, { force: true, confirmDiscard: false });
    }
    return true;
  } catch (err) {
    dom.moduleEditorStatus.textContent = err.message;
    showToast(err.message);
    return false;
  } finally {
    if (dom.moduleMoveConfirm) {
      dom.moduleMoveConfirm.disabled = false;
    }
    updateModuleActionButtons();
  }
}

async function confirmMoveItems() {
  const targetType = getMoveTargetType();
  let moveTarget = null;
  if (targetType === "existing_package") {
    const name = dom.moduleMovePackage ? dom.moduleMovePackage.value : "";
    if (!name) {
      showToast("Select a package to continue.");
      return;
    }
    moveTarget = { type: "existing_package", package_name: name };
  } else if (targetType === "new_package") {
    const name = dom.moduleMoveNewPackage ? dom.moduleMoveNewPackage.value.trim() : "";
    if (!name) {
      showToast("Enter a package name to continue.");
      return;
    }
    moveTarget = { type: "new_package", package_name: name };
  } else if (targetType === "one_off") {
    const filename = dom.moduleMoveOneOff ? dom.moduleMoveOneOff.value.trim() : "";
    if (!filename) {
      showToast("Enter a one-off filename to continue.");
      return;
    }
    moveTarget = { type: "one_off", one_off_filename: filename };
  }
  const succeeded = await operateModuleItems("move", moveTarget);
  if (succeeded) {
    closeMoveModal();
  }
}

async function unassignSelectedItems() {
  const selections = Object.values(state.moduleItemSelections).filter(Boolean);
  if (!selections.length) {
    return;
  }
  if (state.selectedModuleFile && state.selectedModuleFile.includes(".unassigned.")) {
    showToast("Items are already unassigned.");
    return;
  }
  if (!confirmDiscardModuleChanges()) {
    return;
  }
  const count = selections.length;
  if (!window.confirm(`Unassign ${count} item${count === 1 ? "" : "s"}?`)) {
    return;
  }
  await operateModuleItems("unassign");
}

async function deleteSelectedItems() {
  const selections = Object.values(state.moduleItemSelections).filter(Boolean);
  if (!selections.length) {
    return;
  }
  if (!confirmDiscardModuleChanges()) {
    return;
  }
  const count = selections.length;
  const message =
    `Delete ${count} item${count === 1 ? "" : "s"} from the HA config and module files?` +
    " This cannot be undone.";
  if (!window.confirm(message)) {
    return;
  }
  await operateModuleItems("delete");
}

async function syncModules() {
  dom.modulesStatus.textContent = "Syncing YAML Modules...";
  try {
    const data = await requestJSON("/api/modules/sync", { method: "POST" });
    showToast("YAML Modules synced");
    await loadStatus();
    if (!state.moduleFileDirty) {
      await loadModulesIndex();
    }
    const reconciledCount = (data.reconciled_ids || []).length;
    const reconcileNote = reconciledCount
      ? ` Automation IDs reconciled (${reconciledCount}). Review and commit changes.`
      : "";
    if (data.warnings && data.warnings.length) {
      dom.modulesStatus.textContent =
        `Sync complete with warnings: ${data.warnings.join(" | ")}` + reconcileNote;
    } else {
      dom.modulesStatus.textContent = `Sync complete.${reconcileNote}`;
    }
  } catch (err) {
    dom.modulesStatus.textContent = err.message;
    showToast(err.message);
  }
}

function renderPreviewList(container, diffs, emptyMessage) {
  if (!container) {
    return;
  }
  container.innerHTML = "";
  if (!diffs.length) {
    container.innerHTML = `<div class="diff-placeholder">${emptyMessage}</div>`;
    return;
  }
  diffs.forEach((entry) => {
    container.append(createPreviewDiffCard(entry));
  });
}

function createPreviewDiffCard(entry) {
  const details = document.createElement("details");
  details.className = "diff-card";

  const summary = document.createElement("summary");
  const title = document.createElement("div");
  title.className = "diff-title";
  const fileLine = document.createElement("div");
  fileLine.textContent = entry.path || "Unknown file";
  title.append(fileLine);
  summary.append(title);
  details.append(summary);

  const body = document.createElement("div");
  body.className = "diff-body";
  if (!entry.diff || !entry.diff.trim()) {
    body.innerHTML = "<div class=\"diff-placeholder\">No diff available.</div>";
  } else {
    body.innerHTML = "<div class=\"diff-placeholder\">Loading diff...</div>";
    loadDiff2Html()
      .then((diff2Html) => {
        if (!diff2Html || typeof diff2Html.html !== "function") {
          body.innerHTML = "<div class=\"diff-placeholder\">Diff viewer failed to load.</div>";
          return;
        }
        body.innerHTML = diff2Html.html(entry.diff, {
          inputFormat: "diff",
          outputFormat: "side-by-side",
          drawFileList: false,
          matching: "lines",
        });
      })
      .catch((err) => {
        body.innerHTML = `<div class=\"diff-placeholder\">${err.message}</div>`;
      });
  }
  details.append(body);
  return details;
}

async function previewModules() {
  if (dom.modulesPreviewStatus) {
    dom.modulesPreviewStatus.textContent = "Generating preview...";
  }
  renderPreviewList(dom.modulesPreviewBuild, [], "Loading preview...");
  renderPreviewList(dom.modulesPreviewUpdate, [], "Loading preview...");
  try {
    const data = await requestJSON("/api/modules/preview", { method: "POST" });
    renderPreviewList(
      dom.modulesPreviewBuild,
      data.build_diffs || [],
      "No domain file changes."
    );
    renderPreviewList(
      dom.modulesPreviewUpdate,
      data.update_diffs || [],
      "No module file changes."
    );
    if (dom.modulesPreviewStatus) {
      if (data.warnings && data.warnings.length) {
        dom.modulesPreviewStatus.textContent =
          `Preview complete with warnings: ${data.warnings.join(" | ")}`;
      } else {
        dom.modulesPreviewStatus.textContent = "Preview complete.";
      }
    }
  } catch (err) {
    if (dom.modulesPreviewStatus) {
      dom.modulesPreviewStatus.textContent = err.message;
    }
    showToast(err.message);
  }
}

function bindEvents() {
  qsa(".tab-btn[data-tab]").forEach((btn) => {
    btn.addEventListener("click", () => setTab(btn.dataset.tab));
  });

  dom.statusRefresh.addEventListener("click", loadStatus);
  dom.remoteRefresh.addEventListener("click", refreshRemoteStatus);

  dom.commitStaged.addEventListener("click", () => commitChanges(false));
  dom.commitAll.addEventListener("click", () => commitChanges(true));
  dom.pullBtn.addEventListener("click", pullChanges);
  dom.pushBtn.addEventListener("click", pushChanges);

  dom.stageAll.addEventListener("click", () => {
    const changes = (state.status && state.status.changes) || [];
    const files = changes
      .filter((change) => change.unstaged || change.untracked)
      .map((change) => change.path);
    stageFiles(files);
  });
  dom.unstageAll.addEventListener("click", () => {
    const changes = (state.status && state.status.changes) || [];
    const files = changes.filter((change) => change.staged).map((change) => change.path);
    unstageFiles(files);
  });
  if (dom.treeStageSelected) {
    dom.treeStageSelected.addEventListener("click", () => {
      const selections = Object.values(state.gitTreeSelections);
      const files = selections
        .filter((entry) => entry.unstaged || entry.untracked)
        .map((entry) => entry.path);
      stageFiles(files);
    });
  }
  if (dom.treeUnstageSelected) {
    dom.treeUnstageSelected.addEventListener("click", () => {
      const selections = Object.values(state.gitTreeSelections);
      const files = selections.filter((entry) => entry.staged).map((entry) => entry.path);
      unstageFiles(files);
    });
  }
  qsa("#git-tree-mode .segmented-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.gitTreeMode = btn.dataset.mode;
      qsa("#git-tree-mode .segmented-btn").forEach((el) =>
        el.classList.toggle("is-active", el === btn)
      );
      loadGitFiles();
    });
  });
  if (dom.gitTreeIgnored) {
    dom.gitTreeIgnored.addEventListener("change", () => {
      state.gitTreeIncludeIgnored = dom.gitTreeIgnored.checked;
      loadGitFiles();
    });
  }
  if (dom.fileViewerClose) {
    dom.fileViewerClose.addEventListener("click", closeFilePreview);
  }
  if (dom.fileViewerIgnore) {
    dom.fileViewerIgnore.addEventListener("click", () => {
      const path = state.filePreviewPath || dom.fileViewerIgnore.dataset.path;
      if (path) {
        toggleGitignore(path, dom.fileViewerIgnore);
      }
    });
  }

  qsa("#diff-mode .segmented-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      setDiffMode(btn.dataset.mode);
    });
  });

  dom.branchSelect.addEventListener("change", async (event) => {
    state.selectedBranch = event.target.value;
    await loadCommits(state.selectedBranch);
  });

  dom.resetCommit.addEventListener("click", resetToCommit);

  dom.saveConfig.addEventListener("click", saveConfig);
  if (dom.cliInstallBtn) {
    dom.cliInstallBtn.addEventListener("click", installCli);
  }
  dom.sshGenerateBtn.addEventListener("click", generateSshKey);
  dom.sshLoadBtn.addEventListener("click", loadPublicKey);
  dom.sshTestBtn.addEventListener("click", testSshKey);
  dom.modulesSyncBtn.addEventListener("click", syncModules);
  if (dom.modulesPreviewBtn) {
    dom.modulesPreviewBtn.addEventListener("click", previewModules);
  }
  dom.moduleSelect.addEventListener("change", (event) => {
    const nextId = event.target.value;
    if (!confirmDiscardModuleChanges()) {
      dom.moduleSelect.value = state.selectedModuleId || "";
      return;
    }
    state.selectedModuleId = nextId;
    clearModuleSelection();
    renderModuleFileList(getModuleById(nextId));
  });
  dom.moduleSaveBtn.addEventListener("click", saveModuleFile);
  dom.moduleDeleteBtn.addEventListener("click", deleteModuleFile);
  if (dom.exportRunBtn) {
    dom.exportRunBtn.addEventListener("click", runExport);
  }
  if (dom.exportSaveConfig) {
    dom.exportSaveConfig.addEventListener("click", saveExportConfig);
  }
  qsa(".export-tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => setExportTab(btn.dataset.exportTab));
  });
  if (dom.groupsDestinationType) {
    dom.groupsDestinationType.addEventListener("change", updateGroupsDestinationFields);
  }
  if (dom.groupsSave) {
    dom.groupsSave.addEventListener("click", saveGroup);
  }
  if (dom.groupsDelete) {
    dom.groupsDelete.addEventListener("click", deleteGroup);
  }
  if (dom.groupsClear) {
    dom.groupsClear.addEventListener("click", () => setGroupsEditorSelection(null));
  }
  if (dom.groupsRefresh) {
    dom.groupsRefresh.addEventListener("click", loadGroupsData);
  }
  if (dom.groupsShowUnmanaged) {
    dom.groupsShowUnmanaged.addEventListener("change", renderGroups);
  }
  if (dom.groupsShowIgnored) {
    dom.groupsShowIgnored.addEventListener("change", renderGroups);
  }
  if (dom.groupsRestartAck) {
    dom.groupsRestartAck.addEventListener("click", ackGroupsRestart);
  }
  if (dom.moduleMoveBtn) {
    dom.moduleMoveBtn.addEventListener("click", openMoveModal);
  }
  if (dom.moduleUnassignBtn) {
    dom.moduleUnassignBtn.addEventListener("click", unassignSelectedItems);
  }
  if (dom.moduleDeleteItemsBtn) {
    dom.moduleDeleteItemsBtn.addEventListener("click", deleteSelectedItems);
  }
  if (dom.moduleMoveClose) {
    dom.moduleMoveClose.addEventListener("click", closeMoveModal);
  }
  if (dom.moduleMoveCancel) {
    dom.moduleMoveCancel.addEventListener("click", closeMoveModal);
  }
  if (dom.moduleMoveConfirm) {
    dom.moduleMoveConfirm.addEventListener("click", confirmMoveItems);
  }
  qsa("input[name=\"module-move-type\"]").forEach((input) => {
    input.addEventListener("change", () => setMoveTargetType(input.value));
  });
  if (dom.moduleMovePackage) {
    dom.moduleMovePackage.addEventListener("change", () => {
      updateMoveModalSummary();
      updateMoveModalConfirmState();
    });
  }
  if (dom.moduleMoveNewPackage) {
    dom.moduleMoveNewPackage.addEventListener("input", () => {
      updateMoveModalSummary();
      updateMoveModalConfirmState();
    });
  }
  if (dom.moduleMoveOneOff) {
    dom.moduleMoveOneOff.addEventListener("input", () => {
      updateMoveModalSummary();
      updateMoveModalConfirmState();
    });
  }
  if (dom.moduleMoveModal) {
    dom.moduleMoveModal.addEventListener("click", (event) => {
      if (event.target === dom.moduleMoveModal) {
        closeMoveModal();
      }
    });
  }
}

async function init() {
  bindEvents();
  updateGroupsDestinationFields();
  await loadConfig();
  await loadStatus();
  await loadExportConfig();
  await loadModulesIndex();
  await loadBranches();
  await loadSshStatus();
  if (isModulesTabActive()) {
    startModulesRefresh();
  }
}

init();
