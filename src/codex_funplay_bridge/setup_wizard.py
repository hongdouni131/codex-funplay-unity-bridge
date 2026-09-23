"""Small Windows GUI for validating and deploying a project-local Bridge."""

from __future__ import annotations

import json
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .provisioning import DeploymentPlan, ProvisioningError, create_plan, deploy, preflight


class SetupWizard(ttk.Frame):
    def __init__(self, root: tk.Tk) -> None:
        super().__init__(root, padding=20)
        self.root = root
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.plan: DeploymentPlan | None = None
        self.project_path = tk.StringVar()
        self.funplay_url = tk.StringVar(value="http://127.0.0.1:22166/")
        self.timeout = tk.StringVar(value="10")
        self.status = tk.StringVar(value="请选择 Unity 项目，并粘贴 Funplay MCP Server 显示的 URL。")
        self._build()
        for variable in (self.project_path, self.funplay_url, self.timeout):
            variable.trace_add("write", self._invalidate_plan)
        self.after(100, self._drain_events)

    def _build(self) -> None:
        self.root.title("Codex-Funplay Bridge 配置向导")
        self.root.minsize(680, 390)
        self.grid(sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)

        ttk.Label(self, text="Codex-Funplay Bridge", font=("Segoe UI", 16, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(self, text="为当前 Unity 项目部署独立 Bridge，不会修改 Codex 或 Unity 的全局配置。", wraplength=620).grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 18))

        ttk.Label(self, text="Unity 项目路径").grid(row=2, column=0, sticky="w", pady=5)
        self.project_entry = ttk.Entry(self, textvariable=self.project_path)
        self.project_entry.grid(row=2, column=1, sticky="ew", padx=8, pady=5)
        self.browse_button = ttk.Button(self, text="浏览...", command=self._browse)
        self.browse_button.grid(row=2, column=2, pady=5)

        ttk.Label(self, text="Funplay URL").grid(row=3, column=0, sticky="w", pady=5)
        self.url_entry = ttk.Entry(self, textvariable=self.funplay_url)
        self.url_entry.grid(row=3, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=5)

        ttk.Label(self, text="超时秒数").grid(row=4, column=0, sticky="w", pady=5)
        self.timeout_entry = ttk.Entry(self, textvariable=self.timeout, width=12)
        self.timeout_entry.grid(row=4, column=1, sticky="w", padx=8, pady=5)

        self.validate_button = ttk.Button(self, text="验证配置", command=self._validate)
        self.validate_button.grid(row=5, column=1, sticky="w", padx=8, pady=(18, 10))
        self.deploy_button = ttk.Button(self, text="部署 Bridge", command=self._deploy, state="disabled")
        self.deploy_button.grid(row=5, column=2, sticky="e", pady=(18, 10))

        ttk.Separator(self).grid(row=6, column=0, columnspan=3, sticky="ew", pady=8)
        ttk.Label(self, textvariable=self.status, wraplength=620, justify="left").grid(row=7, column=0, columnspan=3, sticky="nw", pady=(8, 0))

    def _browse(self) -> None:
        selected = filedialog.askdirectory(title="选择 Unity 项目根目录")
        if selected:
            self.project_path.set(selected)

    def _invalidate_plan(self, *_: object) -> None:
        self.plan = None
        self.deploy_button.configure(state="disabled")

    def _create_plan(self) -> DeploymentPlan:
        try:
            timeout = float(self.timeout.get())
        except ValueError as exc:
            raise ProvisioningError("Timeout must be a positive number") from exc
        return create_plan(self.project_path.get(), self.funplay_url.get(), timeout)

    def _validate(self) -> None:
        try:
            plan = self._create_plan()
        except ProvisioningError as exc:
            self._show_error(str(exc))
            return
        self._set_busy("正在检查 Unity 项目、URL 和 Funplay MCP 服务...")
        threading.Thread(target=self._validate_worker, args=(plan,), daemon=True).start()

    def _validate_worker(self, plan: DeploymentPlan) -> None:
        try:
            report = preflight(plan)
            self.events.put(("validated", (plan, report)))
        except Exception as exc:
            self.events.put(("error", str(exc)))

    def _deploy(self) -> None:
        if self.plan is None:
            return
        existing = [path for path in self.plan.managed_paths if path.exists()]
        if existing and not messagebox.askyesno(
            "替换已有 Bridge 文件？",
            "以下 Bridge 管理文件已存在，将被替换：\n\n"
            + "\n".join(str(path) for path in existing)
            + "\n\n不会修改 Unity 资源或全局 MCP 设置。",
            parent=self.root,
        ):
            return
        self._set_busy("正在创建项目专用虚拟环境并安装 Bridge...")
        threading.Thread(target=self._deploy_worker, args=(self.plan, bool(existing)), daemon=True).start()

    def _deploy_worker(self, plan: DeploymentPlan, replace_existing: bool) -> None:
        try:
            files = deploy(plan, replace_existing=replace_existing)
            report = preflight(plan)
            self.events.put(("deployed", (files, report)))
        except Exception as exc:
            self.events.put(("error", str(exc)))

    def _drain_events(self) -> None:
        try:
            while True:
                name, payload = self.events.get_nowait()
                if name == "validated":
                    self._finish_validation(*payload)  # type: ignore[arg-type]
                elif name == "deployed":
                    self._finish_deployment(*payload)  # type: ignore[arg-type]
                else:
                    self._show_error(str(payload))
        except queue.Empty:
            pass
        self.after(100, self._drain_events)

    def _finish_validation(self, plan: DeploymentPlan, report: dict[str, object]) -> None:
        self._set_ready()
        if report.get("ok"):
            self.plan = plan
            existing = report["deployment"]["existing_managed_files"]  # type: ignore[index]
            suffix = " 已有 Bridge 文件，部署时会要求确认替换。" if existing else ""
            self.status.set(f"配置验证成功。Funplay 返回 {report['tool_count']} 个工具。{suffix}")
            self.deploy_button.configure(state="normal")
        else:
            self.plan = None
            self.deploy_button.configure(state="disabled")
            self.status.set("验证失败：" + str(report.get("diagnosis", "请查看错误详情。")))
            self._show_error(json.dumps(report, ensure_ascii=False, indent=2))

    def _finish_deployment(self, files: list[Path], report: dict[str, object]) -> None:
        self._set_ready()
        if report.get("ok"):
            self.status.set(f"Bridge 已部署。Funplay 返回 {report['tool_count']} 个工具。可使用 tools\\start_unity_http_stdio_bridge.cmd 启动。")
            messagebox.showinfo("Bridge 已部署", "已创建或更新：\n\n" + "\n".join(str(path) for path in files), parent=self.root)
        else:
            self.status.set("文件已部署，但后续健康检查失败。")
            messagebox.showerror("Bridge 健康检查", json.dumps(report, ensure_ascii=False, indent=2), parent=self.root)

    def _set_busy(self, message: str) -> None:
        self.status.set(message)
        for widget in (self.project_entry, self.browse_button, self.url_entry, self.timeout_entry):
            widget.configure(state="disabled")
        self.validate_button.configure(state="disabled")
        self.deploy_button.configure(state="disabled")

    def _set_ready(self) -> None:
        for widget in (self.project_entry, self.browse_button, self.url_entry, self.timeout_entry):
            widget.configure(state="normal")
        self.validate_button.configure(state="normal")

    def _show_error(self, message: str) -> None:
        self._set_ready()
        self.deploy_button.configure(state="disabled")
        self.status.set("配置未发生变更。")
        messagebox.showerror("Bridge 配置", message, parent=self.root)


def main() -> None:
    root = tk.Tk()
    SetupWizard(root)
    root.mainloop()


if __name__ == "__main__":
    main()
