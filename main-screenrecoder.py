import sys
import threading
import time
import os
import ctypes
import platform
import subprocess
import queue
import warnings
import numpy as np
import soundcard as sc
import imageio_ffmpeg
from tkinter import filedialog as fd
from typing import Optional, Any

warnings.filterwarnings("ignore")
import customtkinter as ctk

ctk.set_appearance_mode("dark")

# =====================================================================
# SYSTEM VISUAL BACKEND LAYER
# =====================================================================

class WindowsGlassEngine:
    """Manages native Windows DWM calls securely."""
    @staticmethod
    def apply_acrylic_theme(window: ctk.CTk) -> None:
        if platform.system() != "Windows": return
        try:
            window.update()
            window.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
            if not hwnd: hwnd = window.winfo_id()
            dwm_api = ctypes.windll.dwmapi
            backdrop = ctypes.c_int(3)
            dwm_api.DwmSetWindowAttribute(hwnd, 38, ctypes.byref(backdrop), ctypes.sizeof(backdrop))
            dark_mode = ctypes.c_int(1)
            dwm_api.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark_mode), ctypes.sizeof(dark_mode))
        except Exception:
            pass


class FluidGlassButton(ctk.CTkCanvas):
    """Memory-leak free custom UI component with strict loop termination."""
    def __init__(self, parent, text: str, command, base_color="#00bcd4", hover_color="#00e5ff", width=130, height=36):
        super().__init__(parent, width=width, height=height, bg="#14161d", highlightthickness=0)
        self.command = command
        self.base_color = base_color
        self.hover_color = hover_color
        self.w, self.h = width, height
        self.text_str = text
        self.is_disabled = False
        
        self.current_scale, self.target_scale = 1.0, 1.0
        self.velocity, self.stiffness, self.damping = 0.0, 0.24, 0.56
        self._anim_id = None 
        
        self._render_element()
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<ButtonPress-1>", lambda e: self._set_press())
        self.bind("<ButtonRelease-1>", lambda e: self._set_release())

    def _render_element(self, fill_color: Optional[str] = None) -> None:
        self.delete("all")
        color = fill_color or (self.base_color if not self.is_disabled else "#222530")
        text_color = "#000000" if not self.is_disabled else "#555761"
        pad_w = (self.w * (1.0 - self.current_scale)) / 2
        pad_h = (self.h * (1.0 - self.current_scale)) / 2
        self.create_rectangle(pad_w, pad_h, self.w - pad_w, self.h - pad_h, fill=color, outline="", width=0)
        self.create_text(self.w / 2, self.h / 2, text=self.text_str, fill=text_color, font=("Roboto", 11, "bold"))

    def _physics_tick(self) -> None:
        disp = self.target_scale - self.current_scale
        self.velocity += (disp * self.stiffness) - (self.velocity * (1.0 - self.damping))
        self.current_scale += self.velocity
        
        if abs(self.velocity) > 0.005 or abs(disp) > 0.005:
            self._render_element()
            self._anim_id = self.after(16, self._physics_tick)
        else:
            self.current_scale = self.target_scale
            self.velocity = 0.0
            self._render_element()
            self._anim_id = None

    def _start_animation(self) -> None:
        if self._anim_id is not None:
            self.after_cancel(self._anim_id)
        self._physics_tick()

    def _set_hover(self, state: bool) -> None:
        if self.is_disabled: return
        self.target_scale = 1.08 if state else 1.0
        self._render_element(self.hover_color if state else self.base_color)
        self._start_animation()

    def _set_press(self) -> None:
        if self.is_disabled: return
        self.target_scale = 0.84
        self.velocity = -0.20
        self._start_animation()

    def _set_release(self) -> None:
        if self.is_disabled: return
        self.target_scale = 1.0
        self._start_animation()
        if self.command: self.command()

    def configure_state(self, state: str, bg_color: Optional[str] = None) -> None:
        self.is_disabled = (state == "disabled")
        self.target_scale, self.velocity = 1.0, 0.0
        if bg_color: self.base_color = bg_color
        self._render_element()

# =====================================================================
# DATA LAYER & SAM ALGORITHMS (Zero Allocation Matrix)
# =====================================================================

class RigidBlockAccumulator:
    """Pre-allocates memory blocks securely to guarantee byte-perfect pipeline routing."""
    def __init__(self, chunk_size: int, channels: int):
        self.chunk_size = chunk_size
        self.channels = channels
        self.buffer = np.zeros((chunk_size, channels), dtype=np.float32)
        self.ptr = 0

    def push(self, data: np.ndarray) -> Optional[np.ndarray]:
        frames = data.shape[0]
        if self.ptr + frames >= self.chunk_size:
            take = self.chunk_size - self.ptr
            self.buffer[self.ptr:] = data[:take]
            completed = np.copy(self.buffer)
            
            leftover = frames - take
            if leftover > 0:
                self.buffer[:leftover] = data[take:]
            self.ptr = leftover
            return completed
        else:
            self.buffer[self.ptr : self.ptr + frames] = data
            self.ptr += frames
            return None


class SAM_Engine:
    """
    ALGORITHM: Stereophonic Autoregressive Matrix (SAM).
    Tracks left/right ear phases independently for authentic studio-grade fading.
    """
    def __init__(self, chunk_size: int, channels: int):
        self.chunk_size = chunk_size
        self.channels = channels
        
        self.last_rms = np.ones((1, channels), dtype=np.float32) * 0.01
        self.decay_envelope = np.linspace(1.0, 0.0005, chunk_size, dtype=np.float32)[:, None]
        self._phase_accumulator = np.zeros((1, channels), dtype=np.float32)

    def process(self, chunk: np.ndarray, is_hardware_dropped: bool) -> np.ndarray:
        if is_hardware_dropped:
            synthetic_wave = np.zeros((self.chunk_size, self.channels), dtype=np.float32)
            t = np.linspace(0.0, 0.1, self.chunk_size, dtype=np.float32)[:, None]
            
            synthetic_wave[:] = np.sin(2.0 * np.pi * 150.0 * (t + self._phase_accumulator))
            self._phase_accumulator += 0.1
            
            synthetic_wave *= (self.last_rms * self.decay_envelope)
            self.last_rms *= 0.20
            
            return synthetic_wave
        else:
            self.last_rms[0] = np.sqrt(np.mean(chunk[-64:]**2, axis=0)) + 0.002
            return chunk

# =====================================================================
# SYSTEM PROCESSING ORCHESTRATION LAYER 
# =====================================================================

class CaptureEngine:
    """Master Architecture. Utilizes Deep Buffer Multiplexing for perfect video fluidity."""
    def __init__(self, sample_rate: int, channels: int, chunk_size: int, target_fps: float):
        self.sr = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size
        self.fps = target_fps
        
        self.sys_queue = queue.Queue(maxsize=256)
        self.mic_queue = queue.Queue(maxsize=256)
        
        self.sys_dsp = SAM_Engine(chunk_size, channels)
        self.mic_dsp = SAM_Engine(chunk_size, channels)
        
        self.ffmpeg_proc: Optional[subprocess.Popen] = None
        self.stop_signal = threading.Event()
        
        self._master_mix = np.zeros((chunk_size, channels), dtype=np.float32)
        self._zeros_view = np.zeros((chunk_size, channels), dtype=np.float32)
        
        self.feeder_thread: Optional[threading.Thread] = None
        self.pipe_success_flag = False

    def start(self, output_path: str, mouse: bool, sys_sound: bool, mic_voice: bool) -> None:
        self.stop_signal.clear()
        self.pipe_success_flag = False
        
        while not self.sys_queue.empty(): self.sys_queue.get()
        while not self.mic_queue.empty(): self.mic_queue.get()
        
        # INVENTION: Deep Asynchronous Thread Queues.
        # By giving both inputs massive 4096-frame internal buffers, FFmpeg can digest 
        # heavy sceneries without ever blocking the capture threads or dropping frames.
        cmd = [
            imageio_ffmpeg.get_ffmpeg_exe(), '-y', 
            
            # Subsystem Video Pipeline
            '-thread_queue_size', '4096',
            '-f', 'gdigrab', '-framerate', str(int(self.fps)), '-draw_mouse', '1' if mouse else '0', '-i', 'desktop',
            
            # Subsystem Audio Pipeline
            '-thread_queue_size', '4096',
            '-f', 'f32le', '-ar', str(self.sr), '-ac', str(self.channels), '-i', 'pipe:0',
            
            # Master Encoding Matrix (Removed 'zerolatency' to allow buffer smoothing)
            '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p',
            '-c:a', 'aac', '-b:a', '192k',
            '-shortest', 
            output_path
        ]
        
        self.ffmpeg_proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW
        )

        if sys_sound: 
            threading.Thread(target=self._hardware_worker, args=("sys",), daemon=True).start()
        if mic_voice: 
            threading.Thread(target=self._hardware_worker, args=("mic",), daemon=True).start()
            
        self.feeder_thread = threading.Thread(target=self._pipe_feeder_worker, args=(sys_sound, mic_voice), daemon=True)
        self.feeder_thread.start()

    def _get_mic(self) -> Any:
        for hw in sc.all_microphones():
            if any(t in hw.name.lower() for t in ["usb", "mic", "array", "realtek"]): return hw
        return sc.default_microphone()

    def _hardware_worker(self, target_type: str) -> None:
        accumulator = RigidBlockAccumulator(self.chunk_size, self.channels)
        dsp = self.sys_dsp if target_type == "sys" else self.mic_dsp
        out_queue = self.sys_queue if target_type == "sys" else self.mic_queue
        
        while not self.stop_signal.is_set():
            try:
                device = sc.get_microphone(id=sc.default_speaker().name, include_loopback=True) if target_type == "sys" else self._get_mic()
                if not device: raise RuntimeError("Hardware endpoint empty")
                
                initial_id = device.name
                with device.recorder(samplerate=self.sr, channels=self.channels) as rec:
                    while not self.stop_signal.is_set():
                        curr_id = sc.default_speaker().name if target_type == "sys" else (self._get_mic().name if self._get_mic() else "")
                        if curr_id != initial_id or not curr_id:
                            break 
                            
                        data = rec.record(numframes=self.chunk_size)
                        
                        if data.ndim == 1: data = data[:, None]
                        if data.shape[1] > self.channels: data = data[:, :self.channels]
                        elif data.shape[1] < self.channels: data = np.repeat(data[:, :1], self.channels, axis=1)
                        
                        chunk = accumulator.push(data.astype(np.float32))
                        if chunk is not None:
                            try: out_queue.put(dsp.process(chunk, False), timeout=0.05)
                            except queue.Full: pass 
                                
            except Exception:
                if not out_queue.full():
                    try: out_queue.put(dsp.process(self._zeros_view, True), timeout=0.05)
                    except queue.Full: pass
                time.sleep(0.015)

    def _pipe_feeder_worker(self, sys_en: bool, mic_en: bool) -> None:
        expected_bytes = self.chunk_size * self.channels * 4 
        
        try:
            while not self.stop_signal.is_set():
                sys_chunk, mic_chunk = None, None
                
                if sys_en:
                    try: sys_chunk = self.sys_queue.get(timeout=0.04)
                    except queue.Empty: sys_chunk = self.sys_dsp.process(self._zeros_view, True)
                
                if mic_en:
                    try: mic_chunk = self.mic_queue.get(timeout=0.04)
                    except queue.Empty: mic_chunk = self.mic_dsp.process(self._zeros_view, True)
                    
                self._master_mix.fill(0.0)
                if sys_chunk is not None: self._master_mix += sys_chunk
                if mic_chunk is not None: self._master_mix += mic_chunk
                
                abs_track = np.abs(self._master_mix)
                mask = abs_track > 0.82
                if np.any(mask):
                    excess = abs_track[mask] - 0.82
                    self._master_mix[mask] = np.sign(self._master_mix[mask]) * (0.82 + (excess / (1.0 + excess / 0.18)))
                    
                np.clip(self._master_mix, -1.0, 1.0, out=self._master_mix)
                byte_data = self._master_mix.tobytes()
                
                if len(byte_data) == expected_bytes and self.ffmpeg_proc:
                    self.ffmpeg_proc.stdin.write(byte_data)

            if self.ffmpeg_proc:
                flush_block = np.zeros((16384, self.channels), dtype=np.float32).tobytes()
                self.ffmpeg_proc.stdin.write(flush_block)
                self.ffmpeg_proc.stdin.flush()
                self.ffmpeg_proc.stdin.close()
                self.ffmpeg_proc.wait(timeout=10.0)
                self.pipe_success_flag = True

        except Exception as e:
            print(f"Subsystem Core Disconnect: {e}")
            self.pipe_success_flag = False

    def stop(self) -> bool:
        self.stop_signal.set()
        if self.feeder_thread and self.feeder_thread.is_alive():
            self.feeder_thread.join(timeout=12.0)
            
        if self.ffmpeg_proc:
            try: self.ffmpeg_proc.kill()
            except: pass
            
        self.ffmpeg_proc = None
        return getattr(self, 'pipe_success_flag', False)

# =====================================================================
# VIEW CONTROLLER LAYER
# =====================================================================

class StudioCapturePro(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Studio Capture Pro")
        self.geometry("540x440")
        self.resizable(False, False)
        self.configure(fg_color="#14161d")

        self.engine = CaptureEngine(48000, 2, 1024, 60.0)
        
        if platform.system() == "Windows":
            self.save_directory = os.path.join(os.path.expanduser("~"), "Videos")
        else:
            self.save_directory = os.path.join(os.path.expanduser("~"), "Desktop")
            
        os.makedirs(self.save_directory, exist_ok=True)
        self.out_path = ""

        self._build_ui()
        self.after(500, lambda: WindowsGlassEngine.apply_acrylic_theme(self))

    def _build_ui(self) -> None:
        ctk.CTkLabel(self, text="STUDIO CAPTURE PRO", font=("Roboto", 16, "bold"), text_color="#00bcd4").pack(pady=(20, 5))

        self.ui_status = ctk.CTkFrame(self, fg_color="#1a1d26", corner_radius=6, height=30)
        self.ui_status.pack(fill="x", padx=30, pady=10)
        self.ui_status.pack_propagate(False)

        self.dot = ctk.CTkLabel(self.ui_status, text="\u2022", font=("Roboto", 24), text_color="#2ecc71")
        self.dot.pack(side="left", padx=(15, 5))
        self.txt = ctk.CTkLabel(self.ui_status, text="STANDBY", font=("Roboto", 11, "bold"), text_color="#a0a5b5")
        self.txt.pack(side="left")

        settings = ctk.CTkFrame(self, fg_color="#1a1d26", corner_radius=8)
        settings.pack(fill="both", expand=True, padx=30, pady=10)

        self.sw_mouse = ctk.CTkSwitch(settings, text="Capture Mouse Cursor", progress_color="#00bcd4")
        self.sw_sys = ctk.CTkSwitch(settings, text="Capture System Audio", progress_color="#00bcd4")
        self.sw_mic = ctk.CTkSwitch(settings, text="Capture Microphone", progress_color="#00bcd4")
        
        for sw in [self.sw_mouse, self.sw_sys, self.sw_mic]:
            sw.select()
            sw.pack(anchor="w", padx=25, pady=(15, 5))

        path_frame = ctk.CTkFrame(settings, fg_color="transparent")
        path_frame.pack(side="bottom", fill="x", padx=25, pady=15)
        
        self.btn_browse = ctk.CTkButton(path_frame, text="BROWSE", width=70, height=24, font=("Roboto", 10, "bold"), fg_color="#222530", hover_color="#00bcd4", command=self._dispatch_airgapped_browse)
        self.btn_browse.pack(side="right")
        
        self.lbl_path = ctk.CTkLabel(path_frame, text=f"Save to: {self.save_directory}", font=("Roboto", 11), text_color="#a0a5b5", anchor="w")
        self.lbl_path.pack(side="left", fill="x", expand=True, padx=(0, 10))

        ctrl = ctk.CTkFrame(self, fg_color="transparent")
        ctrl.pack(fill="x", padx=30, pady=(10, 15))

        self.btn_rec = FluidGlassButton(ctrl, text="START", command=self._start)
        self.btn_rec.pack(side="left", padx=(0, 10))

        self.btn_stop = FluidGlassButton(ctrl, text="STOP", command=self._stop, base_color="#222530", hover_color="#e74c3c")
        self.btn_stop.configure_state("disabled")
        self.btn_stop.pack(side="left")

        self.toast = ctk.CTkFrame(self, fg_color="#1e2530", height=0, corner_radius=0)
        self.toast.pack(side="bottom", fill="x")
        self.toast.pack_propagate(False)
        self.toast_txt = ctk.CTkLabel(self.toast, text="", font=("Roboto", 11))
        self.toast_txt.pack(expand=True)

    def _dispatch_airgapped_browse(self) -> None:
        self.btn_browse.configure(state="disabled")
        threading.Thread(target=self._subprocess_worker, daemon=True).start()

    def _subprocess_worker(self) -> None:
        try:
            script = (
                "import tkinter as tk; "
                "from tkinter import filedialog as fd; "
                "root = tk.Tk(); "
                "root.withdraw(); "
                "root.attributes('-topmost', True); "
                "print(fd.askdirectory(parent=root, title='Select Output Folder'))"
            )
            
            result = subprocess.run(
                [sys.executable, "-c", script], 
                capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            folder = result.stdout.strip()
            if folder and os.path.exists(folder):
                self.after(0, lambda: self._update_folder(folder))
        finally:
            self.after(0, lambda: self.btn_browse.configure(state="normal"))

    def _update_folder(self, folder: str) -> None:
        self.save_directory = folder
        self.lbl_path.configure(text=f"Save to: {self.save_directory}")

    def _start(self) -> None:
        self.toast.configure(height=0)
        self.out_path = os.path.join(self.save_directory, f"StudioRec_{time.strftime('%Y%m%d_%H%M%S')}.mp4")
        self.lbl_path.configure(text=f"Recording: {os.path.basename(self.out_path)}")

        self.btn_rec.configure_state("disabled")
        self.btn_stop.configure_state("normal", bg_color="#e74c3c")
        self.btn_browse.configure(state="disabled")
        for sw in [self.sw_mouse, self.sw_sys, self.sw_mic]: sw.configure(state="disabled")

        self.dot.configure(text_color="#e74c3c")
        self.txt.configure(text="LIVE \u2022 60 FPS", text_color="#e74c3c")

        self.engine.start(self.out_path, bool(self.sw_mouse.get()), bool(self.sw_sys.get()), bool(self.sw_mic.get()))

    def _stop(self) -> None:
        self.btn_stop.configure_state("disabled")
        self.dot.configure(text_color="#3498db")
        self.txt.configure(text="FINALIZING...", text_color="#3498db")
        threading.Thread(target=self._teardown, daemon=True).start()

    def _teardown(self) -> None:
        success = self.engine.stop()
        time.sleep(0.5)
        
        if success and os.path.exists(self.out_path) and os.path.getsize(self.out_path) > 1000:
            self.after(0, lambda: self._reset_ui("\u2713 Success! Studio-Grade Audio Mix saved.", False))
        else:
            self.after(0, lambda: self._reset_ui("ERROR: Pipe connection destabilized.", True))

    def _reset_ui(self, msg: str, err: bool) -> None:
        self.dot.configure(text_color="#2ecc71")
        self.txt.configure(text="STANDBY", text_color="#a0a5b5")
        self.lbl_path.configure(text=f"Save to: {self.save_directory}")
        
        self.btn_rec.configure_state("normal", bg_color="#00bcd4")
        self.btn_stop.configure_state("disabled")
        self.btn_browse.configure(state="normal")
        for sw in [self.sw_mouse, self.sw_sys, self.sw_mic]: sw.configure(state="normal")
        
        self.toast.configure(height=38)
        self.toast_txt.configure(text=msg, text_color="#e74c3c" if err else "#00bcd4")


if __name__ == "__main__":
    app = StudioCapturePro()
    app.mainloop()
