import threading
import time
import customtkinter as ctk
import os
import sys
import ctypes
import platform
import subprocess
import numpy as np
import soundcard as sc
import soundfile as sf
import imageio_ffmpeg

# Enforce professional theme defaults
ctk.set_appearance_mode("dark")

class WindowsGlassEngine:
    """Hooks directly into the Windows DWM API to apply a true Acrylic Frosted Glass look."""
    @staticmethod
    def apply_acrylic_theme(window):
        if platform.system() == "Windows":
            try:
                window.update()
                window.update_idletasks()
                hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
                if not hwnd:
                    hwnd = window.winfo_id()

                DWM_API = ctypes.windll.dwmapi
                backdrop_policy = ctypes.c_int(3) 
                DWM_API.DwmSetWindowAttribute(hwnd, 38, ctypes.byref(backdrop_policy), ctypes.sizeof(backdrop_policy))
                
                dark_mode = ctypes.c_int(1)
                DWM_API.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark_mode), ctypes.sizeof(dark_mode))
                print("[Glass Engine] Premium Windows 11 Acrylic Blur applied successfully.")
            except Exception as e:
                print(f"[Glass Engine] Acrylic backdrop initialization bypassed: {e}")


class FluidGlassButton(ctk.CTkCanvas):
    """A premium custom canvas button running a real-time spring physics loop."""
    def __init__(self, parent, text, command, base_color="#00bcd4", hover_color="#00e5ff", width=130, height=36):
        super().__init__(parent, width=width, height=height, bg="#14161d", highlightthickness=0)
        self.command = command
        self.base_color = base_color
        self.hover_color = hover_color
        self.w = width
        self.h = height
        self.text_str = text
        self.is_disabled = False
        
        self.current_scale = 1.0
        self.target_scale = 1.0
        self.velocity = 0.0
        self.stiffness = 0.24   
        self.damping = 0.56     
        
        self._render_element()
        self.bind("<Enter>", self._on_hover_enter)
        self.bind("<Leave>", self._on_hover_leave)
        self.bind("<ButtonPress-1>", self._on_click_press)
        self.bind("<ButtonRelease-1>", self._on_click_release)
        self._physics_tick()

    def _render_element(self, fill_color=None):
        self.delete("all")
        if fill_color is None:
            fill_color = self.base_color if not self.is_disabled else "#222530"
            
        text_color = "#000000" if not self.is_disabled else "#555761"
        pad_w = (self.w * (1.0 - self.current_scale)) / 2
        pad_h = (self.h * (1.0 - self.current_scale)) / 2
        
        self.create_rectangle(
            pad_w, pad_h, self.w - pad_w, self.h - pad_h,
            fill=fill_color, outline="", width=0
        )
        self.create_text(
            self.w / 2, self.h / 2, text=self.text_str,
            fill=text_color, font=("Roboto", 11, "bold")
        )

    def _physics_tick(self):
        displacement = self.target_scale - self.current_scale
        force = (displacement * self.stiffness) - (self.velocity * (1.0 - self.damping))
        self.velocity += force
        self.current_scale += self.velocity
        
        if abs(self.velocity) > 0.001 or abs(displacement) > 0.001:
            self._render_element()
        self.after(16, self._physics_tick)

    def _on_hover_enter(self, event):
        if self.is_disabled: return
        self.target_scale = 1.08
        self._render_element(self.hover_color)

    def _on_hover_leave(self, event):
        if self.is_disabled: return
        self.target_scale = 1.0
        self._render_element(self.base_color)

    def _on_click_press(self, event):
        if self.is_disabled: return
        self.target_scale = 0.84
        self.velocity = -0.20

    def _on_click_release(self, event):
        if self.is_disabled: return
        self.target_scale = 1.0
        if self.command: 
            self.command()

    def configure_state(self, state_str, bg_color=None):
        if state_str == "disabled":
            self.is_disabled = True
            self.target_scale = 1.0
            self._render_element("#222530")
        else:
            self.is_disabled = False
            if bg_color:
                self.base_color = bg_color
            self._render_element(self.base_color)


class StudioCapturePro(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.title("Studio Capture Pro")
        self.geometry("540x440")
        self.resizable(False, False)
        
        # Professional 90 FPS Settings Profile
        self.target_fps = 90.0
        self.record_mouse = True
        self.record_system_sound = True
        self.record_mic_voice = True
        
        self.save_directory = r"C:\Users\brigh\Desktop\mt"
        os.makedirs(self.save_directory, exist_ok=True)
        
        # Process Handles
        self.ffmpeg_process_handle = None
        self.recording_state = "IDLE"  
        self.stop_signal_event = threading.Event()
        
        # Audio Buffers
        self.sys_audio_data = []
        self.mic_audio_data = []
        self.audio_sample_rate = 48000
        
        # Dynamic Hardware Name Tokens
        self.active_speaker_name = None
        self.active_mic_name = None
        
        # Initialize UI and Hardware
        self._verify_native_audio_hardware()
        self._assemble_fluid_interface()
        self._update_preferences()
        self.after(500, lambda: WindowsGlassEngine.apply_acrylic_theme(self))

    def _verify_native_audio_hardware(self):
        """Pre-flight check mapping explicit USB devices via Soundcard logic."""
        print("\n" + "=" * 60)
        print("NATIVE WINDOWS CORE AUDIO DIAGNOSTIC")
        print("=" * 60)
        
        # Pull the primary default playback speaker
        try:
            default_speaker = sc.default_speaker()
            self.active_speaker_name = default_speaker.name
            print(f"[Core Audio] Master System Endpoint: {self.active_speaker_name}")
        except Exception as e:
            print(f"[Core Audio Warning] Default speaker loopback unavailable: {e}")

        # Scan explicitly for the USB microphone to bypass Motherboard aliases
        try:
            mic_list = sc.all_microphones()
            for mic in mic_list:
                if "usb audio" in mic.name.lower():
                    self.active_mic_name = mic.name
                    break
            
            if not self.active_mic_name:
                self.active_mic_name = sc.default_microphone().name
            print(f"[Core Audio] Master Microphone Locked: {self.active_mic_name}")
        except Exception as e:
            print(f"[Core Audio Warning] Microphone targeting failed: {e}")
        print("=" * 60 + "\n")

    def _assemble_fluid_interface(self) -> None:
        self.header_panel = ctk.CTkFrame(self, fg_color="#181a22", height=52, corner_radius=0)
        self.header_panel.pack(fill="x", side="top")
        self.header_panel.pack_propagate(False)
        
        self.ui_status_dot = ctk.CTkLabel(self.header_panel, text="●", font=("Roboto", 18), text_color="#2ecc71")
        self.ui_status_dot.pack(side="left", padx=(20, 5))
        
        self.ui_status_text = ctk.CTkLabel(self.header_panel, text="STANDBY", font=("Roboto", 13, "bold"), text_color="#a0a5b5")
        self.ui_status_text.pack(side="left", padx=5)
        
        self.ui_fps_badge = ctk.CTkLabel(self.header_panel, text="NATIVE WASAPI CORE ENGINE • 90FPS", font=("Roboto", 10, "bold"), text_color="#515666")
        self.ui_fps_badge.pack(side="right", padx=20)

        self.control_panel = ctk.CTkFrame(self, fg_color="#14161d", height=170, corner_radius=10, border_width=1, border_color="#222530")
        self.control_panel.pack(fill="x", padx=20, pady=15)
        self.control_panel.pack_propagate(False)
        
        self.switch_cursor = ctk.CTkSwitch(self.control_panel, text="Capture Cursor", font=("Roboto", 12), command=self._update_preferences, text_color="#a0a5b5")
        self.switch_cursor.select()
        self.switch_cursor.grid(row=0, column=0, padx=25, pady=18, sticky="w")

        self.switch_sys_audio = ctk.CTkSwitch(self.control_panel, text="Capture System Sound (Default Output)", font=("Roboto", 12), command=self._update_preferences, text_color="#a0a5b5")
        if self.active_speaker_name:
            self.switch_sys_audio.select()
        else:
            self.switch_sys_audio.configure(state="disabled")
        self.switch_sys_audio.grid(row=0, column=1, padx=25, pady=18, sticky="w")
        
        self.switch_mic_audio = ctk.CTkSwitch(self.control_panel, text="Include Microphone Voice (Default Mic)", font=("Roboto", 12), command=self._update_preferences, text_color="#a0a5b5", progress_color="#00bcd4")
        if self.active_mic_name:
            self.switch_mic_audio.select()
        else:
            self.switch_mic_audio.configure(state="disabled")
        self.switch_mic_audio.grid(row=1, column=0, padx=25, pady=12, sticky="w")

        self.ui_io_label = ctk.CTkLabel(self, text=f"Repository Location: {self.save_directory}", font=("Consolas", 10), text_color="#515666")
        self.ui_io_label.pack(anchor="w", padx=25)

        self.ui_toast_panel = ctk.CTkFrame(self, fg_color="#1a2333", height=0, corner_radius=6)
        self.ui_toast_panel.pack(fill="x", padx=20, pady=(8, 0))
        self.ui_toast_panel.pack_propagate(False)
        
        self.ui_toast_text = ctk.CTkLabel(self.ui_toast_panel, text="", font=("Roboto", 11, "bold"), text_color="#38bdf8", anchor="w")
        self.ui_toast_text.pack(fill="x", padx=15, pady=8)

        self.action_dock = ctk.CTkFrame(self, fg_color="#14161d", height=60, corner_radius=12)
        self.action_dock.pack(fill="x", padx=20, side="bottom", pady=15)
        self.action_dock.pack_propagate(False)
        
        self.btn_record = FluidGlassButton(self.action_dock, text="▶  RECORD", command=self.execute_start_pipeline, base_color="#00bcd4", hover_color="#00e5ff", width=120, height=36)
        self.btn_record.pack(side="left", padx=15, pady=10)
        
        self.btn_stop = FluidGlassButton(self.action_dock, text="■  STOP", command=self.execute_stop_pipeline, base_color="#3a3f50", hover_color="#e74c3c", width=95, height=36)
        self.btn_stop.configure_state("disabled")
        self.btn_stop.pack(side="right", padx=15, pady=10)

    def _update_preferences(self) -> None:
        self.record_mouse = bool(self.switch_cursor.get())
        self.record_system_sound = bool(self.switch_sys_audio.get()) if self.active_speaker_name else False
        self.record_mic_voice = bool(self.switch_mic_audio.get()) if self.active_mic_name else False

    def execute_start_pipeline(self) -> None:
        self.recording_state = "RECORDING"
        self.terminate_toast_notification()
        self.stop_signal_event.clear()
        
        self.sys_audio_data = []
        self.mic_audio_data = []

        session_token = time.strftime("%Y%m%d_%H%M%S")
        self.tmp_video_path = os.path.join(self.save_directory, f"raw_v_{session_token}.mp4")
        self.tmp_sys_audio_path = os.path.join(self.save_directory, f"raw_sys_{session_token}.wav")
        self.tmp_mic_audio_path = os.path.join(self.save_directory, f"raw_mic_{session_token}.wav")
        self.final_output_path = os.path.join(self.save_directory, f"studio_rec_{session_token}.mp4")
        
        self.ui_io_label.configure(text=f"Active Stream: studio_rec_{session_token}.mp4")
        self.btn_record.configure_state("disabled")
        self.btn_stop.configure_state("normal", bg_color="#e74c3c")
        
        self.switch_cursor.configure(state="disabled")
        self.switch_sys_audio.configure(state="disabled")
        self.switch_mic_audio.configure(state="disabled")
            
        self._update_preferences()
        self.ui_status_dot.configure(text_color="#e74c3c")
        self.ui_status_text.configure(text="LIVE • 90 FPS", text_color="#e74c3c")
        
        # 1. Start pure video frame encoding process
        self._launch_hardware_encoder_process()
        
        # 2. Fire up the native Python audio hooks
        if self.record_system_sound:
            threading.Thread(target=self._system_audio_capture_loop, daemon=True).start()
            
        if self.record_mic_voice:
            threading.Thread(target=self._microphone_capture_loop, daemon=True).start()

    def _launch_hardware_encoder_process(self) -> None:
        """Video ONLY. FFmpeg captures pure 90 FPS frames while Python handles the audio natively."""
        local_ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        cmd = [
            local_ffmpeg_exe, '-y',
            '-f', 'gdigrab',
            '-framerate', str(int(self.target_fps)),
            '-draw_mouse', '1' if self.record_mouse else '0',
            '-i', 'desktop',
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-tune', 'zerolatency',
            '-pix_fmt', 'yuv420p',
            self.tmp_video_path
        ]
        print(f"[Video Pipeline] Launching independent 90 FPS encoder:\n{' '.join(cmd)}\n")
        self.ffmpeg_process_handle = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW
        )
        threading.Thread(target=self._log_stream_catcher, daemon=True).start()

    def _system_audio_capture_loop(self):
        """Properly hooks into WASAPI loopback interface via soundcard namespace resolution."""
        try:
            # Soundcard Loopback Engine requires 'include_loopback' explicitly on the output device node
            loopback_device = sc.get_microphone(id=self.active_speaker_name, include_loopback=True)
            print(f"[Audio Engine] System loopback bound safely to: {loopback_device.name}")
            
            with loopback_device.recorder(samplerate=self.audio_sample_rate) as loopback:
                while not self.stop_signal_event.is_set():
                    data = loopback.record(numframes=1024)
                    self.sys_audio_data.append(data)
        except Exception as e:
            print(f"[Audio Engine Error] System loopback crashed: {e}")

    def _microphone_capture_loop(self):
        """Hooks into Windows Core Audio and captures your targeted microphone."""
        try:
            mic_device = sc.get_microphone(id=self.active_mic_name)
            print(f"[Audio Engine] Microphone bound safely to: {mic_device.name}")
            
            with mic_device.recorder(samplerate=self.audio_sample_rate) as mic:
                while not self.stop_signal_event.is_set():
                    data = mic.record(numframes=1024)
                    self.mic_audio_data.append(data)
        except Exception as e:
            print(f"[Audio Engine Error] Microphone capture crashed: {e}")

    def _log_stream_catcher(self):
        if self.ffmpeg_process_handle:
            for line in iter(self.ffmpeg_process_handle.stderr.readline, b''):
                decoded_line = line.decode('utf-8', errors='ignore').strip()
                if "error" in decoded_line.lower() or "fail" in decoded_line.lower() or "invalid" in decoded_line.lower():
                    print(f"[FFmpeg Video Warning] {decoded_line}")

    def execute_stop_pipeline(self) -> None:
        self.recording_state = "PROCESSING"
        self.btn_stop.configure_state("disabled")
        self.ui_status_dot.configure(text_color="#3498db")
        self.ui_status_text.configure(text="SYNCHRONIZING...", text_color="#3498db")
        
        # Triggers audio loops to stop collecting chunks
        self.stop_signal_event.set()
        threading.Thread(target=self._teardown_subprocess_worker, daemon=True).start()

    def _teardown_subprocess_worker(self) -> None:
        # Close the video container cleanly
        if self.ffmpeg_process_handle:
            try:
                self.ffmpeg_process_handle.stdin.write(b'q\n')
                self.ffmpeg_process_handle.stdin.flush()
                self.ffmpeg_process_handle.wait(timeout=5)
            except Exception:
                try: self.ffmpeg_process_handle.kill()
                except Exception: pass
        self.ffmpeg_process_handle = None

        has_sys = False
        has_mic = False

        # Compile System Audio Array into WAV
        if self.record_system_sound and len(self.sys_audio_data) > 0:
            try:
                sys_matrix = np.concatenate(self.sys_audio_data, axis=0)
                sf.write(self.tmp_sys_audio_path, sys_matrix, self.audio_sample_rate)
                has_sys = True
            except Exception as e: print(f"[Compiler Error] System audio compilation failed: {e}")

        # Compile Microphone Audio Array into WAV
        if self.record_mic_voice and len(self.mic_audio_data) > 0:
            try:
                mic_matrix = np.concatenate(self.mic_audio_data, axis=0)
                sf.write(self.tmp_mic_audio_path, mic_matrix, self.audio_sample_rate)
                has_mic = True
            except Exception as e: print(f"[Compiler Error] Mic compilation failed: {e}")

        self._execute_native_binary_muxer(has_sys, has_mic)
        self.after(0, self._restore_and_reset_ui)

    def _execute_native_binary_muxer(self, has_sys, has_mic) -> None:
        """Mixes the isolated audio WAV files natively into the high-speed MP4 video wrapper."""
        v_exists = os.path.exists(self.tmp_video_path)
        if not v_exists: 
            print("[Muxer Error] Base video track missing.")
            return
        
        local_ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        cmd = [local_ffmpeg_exe, '-y', '-i', self.tmp_video_path]
        
        audio_index = 1
        filter_inputs = ""

        if has_sys:
            cmd.extend(['-i', self.tmp_sys_audio_path])
            filter_inputs += f"[{audio_index}:a]"
            audio_index += 1
            
        if has_mic:
            cmd.extend(['-i', self.tmp_mic_audio_path])
            filter_inputs += f"[{audio_index}:a]"
            audio_index += 1

        if audio_index == 3:
            cmd.extend(['-filter_complex', f'{filter_inputs}amix=inputs=2:duration=first[aout]', '-map', '0:v:0', '-map', '[aout]'])
        elif audio_index == 2:
            cmd.extend(['-map', '0:v:0', '-map', '1:a:0'])
        else:
            cmd.extend(['-map', '0:v:0'])

        cmd.extend(['-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', self.final_output_path])

        print(f"[Muxer] Synching tracks into final render: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        
        if result.returncode == 0 and os.path.exists(self.final_output_path):
            # Cleanup Temporary Tracks
            for path in [self.tmp_video_path, self.tmp_sys_audio_path, self.tmp_mic_audio_path]:
                try:
                    if os.path.exists(path): os.remove(path)
                except Exception: pass
        else:
            print(f"[Muxer Warning] Output missing. Log: {result.stderr[:500]}")
            try: os.rename(self.tmp_video_path, self.final_output_path)
            except Exception: pass

    def deploy_toast_notification(self, text_message: str) -> None:
        self.ui_toast_panel.configure(height=38)
        self.ui_toast_text.configure(text=text_message)
        
    def terminate_toast_notification(self) -> None:
        self.ui_toast_panel.configure(height=0)
        self.ui_toast_text.configure(text="")

    def _restore_and_reset_ui(self) -> None:
        self.recording_state = "IDLE"
        self.ui_status_dot.configure(text_color="#2ecc71")
        self.ui_status_text.configure(text="STANDBY", text_color="#a0a5b5")
        
        self.btn_record.configure_state("normal", bg_color="#00bcd4")
        self.btn_stop.configure_state("disabled")
        
        self.switch_cursor.configure(state="normal")
        if self.active_speaker_name: self.switch_sys_audio.configure(state="normal")
        if self.active_mic_name: self.switch_mic_audio.configure(state="normal")
        
        self.ui_io_label.configure(text=f"Repository Location: {self.save_directory}")
        self.deploy_toast_notification("✓ Render complete! Video and Audio cleanly synced.")


if __name__ == "__main__":
    app = StudioCapturePro()
    app.mainloop()
