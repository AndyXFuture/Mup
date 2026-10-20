#include "flutter_window.h"

#include <flutter/standard_method_codec.h>

#include <optional>

#include "flutter/generated_plugin_registrant.h"

FlutterWindow* FlutterWindow::active_instance_ = nullptr;

FlutterWindow::FlutterWindow(const flutter::DartProject& project)
    : project_(project) {}

FlutterWindow::~FlutterWindow() {}

bool FlutterWindow::OnCreate() {
  if (!Win32Window::OnCreate()) {
    return false;
  }

  RECT frame = GetClientArea();

  // The size here must match the window dimensions to avoid unnecessary surface
  // creation / destruction in the startup path.
  flutter_controller_ = std::make_unique<flutter::FlutterViewController>(
      frame.right - frame.left, frame.bottom - frame.top, project_);
  // Ensure that basic setup of the controller was successful.
  if (!flutter_controller_->engine() || !flutter_controller_->view()) {
    return false;
  }
  RegisterPlugins(flutter_controller_->engine());
  SetChildContent(flutter_controller_->view()->GetNativeWindow());

  media_channel_ =
      std::make_unique<flutter::MethodChannel<flutter::EncodableValue>>(
          flutter_controller_->engine()->messenger(), "mup/windows/media",
          &flutter::StandardMethodCodec::GetInstance());
  media_channel_->SetMethodCallHandler(
      [this](const auto& call, auto result) {
        if (call.method_name() == "start") {
          if (keyboard_hook_ == nullptr) {
            active_instance_ = this;
            keyboard_hook_ = ::SetWindowsHookExW(
                WH_KEYBOARD_LL, &FlutterWindow::KeyboardHookProc,
                ::GetModuleHandleW(nullptr), 0);
          }
          result->Success(flutter::EncodableValue(keyboard_hook_ != nullptr));
        } else if (call.method_name() == "stop") {
          StopMediaHook();
          result->Success();
        } else {
          result->NotImplemented();
        }
      });

  // Keep the native window hidden until Dart has restored the saved bounds and
  // decided whether this is a normal launch or a silent tray launch.
  flutter_controller_->ForceRedraw();

  return true;
}

void FlutterWindow::OnDestroy() {
  StopMediaHook();
  if (media_channel_) {
    media_channel_->SetMethodCallHandler(nullptr);
    media_channel_ = nullptr;
  }
  if (flutter_controller_) {
    flutter_controller_ = nullptr;
  }

  Win32Window::OnDestroy();
}

LRESULT
FlutterWindow::MessageHandler(HWND hwnd, UINT const message,
                              WPARAM const wparam,
                              LPARAM const lparam) noexcept {
  static const UINT show_message =
      ::RegisterWindowMessageW(L"YinjueMupFlutterShowWindow");
  if (message == show_message) {
    Show();
    ::SetForegroundWindow(GetHandle());
    return 0;
  }

  // Give Flutter, including plugins, an opportunity to handle window messages.
  if (flutter_controller_) {
    std::optional<LRESULT> result =
        flutter_controller_->HandleTopLevelWindowProc(hwnd, message, wparam,
                                                      lparam);
    if (result) {
      return *result;
    }
  }

  switch (message) {
    case WM_FONTCHANGE:
      flutter_controller_->engine()->ReloadSystemFonts();
      break;
  }

  return Win32Window::MessageHandler(hwnd, message, wparam, lparam);
}

void FlutterWindow::SendMediaAction(const char* action) {
  if (!media_channel_) {
    return;
  }
  flutter::EncodableMap arguments;
  arguments[flutter::EncodableValue("action")] = flutter::EncodableValue(action);
  media_channel_->InvokeMethod(
      "media", std::make_unique<flutter::EncodableValue>(arguments));
}

void FlutterWindow::StopMediaHook() {
  if (keyboard_hook_ != nullptr) {
    ::UnhookWindowsHookEx(keyboard_hook_);
    keyboard_hook_ = nullptr;
  }
  pressed_keys_.clear();
  if (active_instance_ == this) {
    active_instance_ = nullptr;
  }
}

LRESULT CALLBACK FlutterWindow::KeyboardHookProc(int code, WPARAM wparam,
                                                  LPARAM lparam) {
  if (code >= 0 && active_instance_ != nullptr) {
    const auto* key = reinterpret_cast<KBDLLHOOKSTRUCT*>(lparam);
    const bool key_down = (wparam == WM_KEYDOWN || wparam == WM_SYSKEYDOWN);
    const bool key_up = (wparam == WM_KEYUP || wparam == WM_SYSKEYUP);
    if (key != nullptr) {
      if (key_down) {
        if (active_instance_->pressed_keys_.insert(key->vkCode).second) {
          const bool ctrl = (::GetAsyncKeyState(VK_CONTROL) & 0x8000) != 0;
          const bool alt = (::GetAsyncKeyState(VK_MENU) & 0x8000) != 0;
          const char* action = nullptr;
          switch (key->vkCode) {
            case VK_MEDIA_PLAY_PAUSE:
              action = "play_pause";
              break;
            case VK_MEDIA_NEXT_TRACK:
              action = "next";
              break;
            case VK_MEDIA_PREV_TRACK:
              action = "previous";
              break;
            case VK_VOLUME_UP:
              action = "volume_up";
              break;
            case VK_VOLUME_DOWN:
              action = "volume_down";
              break;
            case 'P':
              if (ctrl && alt) action = "play_pause";
              break;
            case VK_RIGHT:
              if (ctrl && alt) action = "next";
              break;
            case VK_LEFT:
              if (ctrl && alt) action = "previous";
              break;
            default:
              break;
          }
          if (action != nullptr) {
            active_instance_->SendMediaAction(action);
            return 1;
          }
        }
      } else if (key_up) {
        active_instance_->pressed_keys_.erase(key->vkCode);
      }
    }
  }
  return ::CallNextHookEx(nullptr, code, wparam, lparam);
}
