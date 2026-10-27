#include <flutter/dart_project.h>
#include <flutter/flutter_view_controller.h>
#include <windows.h>

#include <string>

#include "flutter_window.h"
#include "utils.h"

int APIENTRY wWinMain(_In_ HINSTANCE instance, _In_opt_ HINSTANCE prev,
                      _In_ wchar_t *command_line, _In_ int show_command) {
  const bool test_instance =
      command_line != nullptr &&
      std::wstring(command_line).find(L"--test-instance") !=
          std::wstring::npos;
  // Create the readiness event before taking the mutex. If two launches race,
  // the winning process still owns an event that the losing process can wait
  // on instead of broadcasting to a window that does not exist yet.
  HANDLE ready = test_instance
                     ? nullptr
                     : ::CreateEventW(nullptr, TRUE, FALSE,
                                      L"Local\\YinjueMupFlutterReady");
  HANDLE single_instance = nullptr;
  if (!test_instance) {
    single_instance =
        ::CreateMutexW(nullptr, FALSE, L"Local\\YinjueMupFlutterSingleInstance");
  }
  if (single_instance != nullptr &&
      ::GetLastError() == ERROR_ALREADY_EXISTS) {
    if (ready != nullptr) {
      ::WaitForSingleObject(ready, 8000);
    }
    const UINT show_message =
        ::RegisterWindowMessageW(L"YinjueMupFlutterShowWindow");
    HWND existing = nullptr;
    for (int attempt = 0; attempt < 20 && existing == nullptr; ++attempt) {
      existing = ::FindWindowW(nullptr, L"音珏 - Mup");
      if (existing == nullptr) ::Sleep(100);
    }
    if (existing != nullptr) {
      ShowAndFocusWindow(existing);
    } else {
      ::PostMessageW(HWND_BROADCAST, show_message, 0, 0);
    }
    ::CloseHandle(single_instance);
    if (ready != nullptr) ::CloseHandle(ready);
    return EXIT_SUCCESS;
  }

  // Attach to console when present (e.g., 'flutter run') or create a
  // new console when running with a debugger.
  if (!::AttachConsole(ATTACH_PARENT_PROCESS) && ::IsDebuggerPresent()) {
    CreateAndAttachConsole();
  }

  // Initialize COM, so that it is available for use in the library and/or
  // plugins.
  ::CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);

  flutter::DartProject project(L"data");

  std::vector<std::string> command_line_arguments =
      GetCommandLineArguments();

  project.set_dart_entrypoint_arguments(std::move(command_line_arguments));

  FlutterWindow window(project);
  Win32Window::Point origin(10, 10);
  Win32Window::Size size(1080, 720);
  const wchar_t* window_title =
      test_instance ? L"音珏 - Mup [测试]" : L"音珏 - Mup";
  if (!window.Create(window_title, origin, size)) {
    return EXIT_FAILURE;
  }
  window.SetQuitOnClose(true);

  ::MSG msg;
  while (::GetMessage(&msg, nullptr, 0, 0)) {
    ::TranslateMessage(&msg);
    ::DispatchMessage(&msg);
  }

  ::CoUninitialize();
  if (single_instance != nullptr) {
    ::CloseHandle(single_instance);
  }
  if (ready != nullptr) {
    ::CloseHandle(ready);
  }
  return EXIT_SUCCESS;
}
