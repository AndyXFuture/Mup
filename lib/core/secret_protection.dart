import 'dart:convert';
import 'dart:ffi';
import 'dart:io';
import 'dart:typed_data';

import 'package:ffi/ffi.dart';

/// Encrypts Mup's server password with the current Windows user's DPAPI key.
///
/// The encrypted value can only be decrypted by the same Windows account on
/// this machine. No plaintext credential is written by [protectSecret].
class SecretProtection {
  SecretProtection._();

  static final DynamicLibrary _crypt32 = DynamicLibrary.open('crypt32.dll');
  static final DynamicLibrary _kernel32 = DynamicLibrary.open('kernel32.dll');

  static final _CryptProtectDataDart _protect =
      _crypt32.lookupFunction<_CryptProtectDataNative, _CryptProtectDataDart>(
    'CryptProtectData',
  );
  static final _CryptUnprotectDataDart _unprotect = _crypt32
      .lookupFunction<_CryptUnprotectDataNative, _CryptUnprotectDataDart>(
    'CryptUnprotectData',
  );
  static final _LocalFreeDart _localFree =
      _kernel32.lookupFunction<_LocalFreeNative, _LocalFreeDart>('LocalFree');

  static String protectSecret(String value) {
    if (!Platform.isWindows) {
      throw UnsupportedError('DPAPI is only available on Windows');
    }
    return _transform(value, protect: true);
  }

  static String unprotectSecret(String value) {
    if (!Platform.isWindows) {
      throw UnsupportedError('DPAPI is only available on Windows');
    }
    return _transform(value, protect: false);
  }

  static String _transform(String value, {required bool protect}) {
    final bytes = protect ? utf8.encode(value) : base64Decode(value);
    final inputBytes = calloc<Uint8>(bytes.length);
    final input = calloc<_DataBlob>();
    final output = calloc<_DataBlob>();
    final description =
        protect ? 'Mup server password'.toNativeUtf16() : nullptr;
    try {
      inputBytes.asTypedList(bytes.length).setAll(0, bytes);
      input.ref
        ..cbData = bytes.length
        ..pbData = inputBytes;
      final succeeded = protect
          ? _protect(
              input,
              description,
              nullptr,
              nullptr,
              nullptr,
              0x1, // CRYPTPROTECT_UI_FORBIDDEN
              output,
            )
          : _unprotect(
              input,
              nullptr,
              nullptr,
              nullptr,
              nullptr,
              0x1, // CRYPTPROTECT_UI_FORBIDDEN
              output,
            );
      if (succeeded == 0 || output.ref.pbData == nullptr) {
        throw StateError('Windows DPAPI operation failed');
      }
      final transformed = Uint8List.fromList(
        output.ref.pbData.asTypedList(output.ref.cbData),
      );
      return protect
          ? base64Encode(transformed)
          : utf8.decode(transformed, allowMalformed: false);
    } finally {
      if (protect && description != nullptr) calloc.free(description);
      if (output.ref.pbData != nullptr) {
        _localFree(output.ref.pbData.cast<Void>());
      }
      calloc
        ..free(inputBytes)
        ..free(input)
        ..free(output);
    }
  }
}

final class _DataBlob extends Struct {
  @Uint32()
  external int cbData;

  external Pointer<Uint8> pbData;
}

typedef _CryptProtectDataNative = Int32 Function(
  Pointer<_DataBlob>,
  Pointer<Utf16>,
  Pointer<_DataBlob>,
  Pointer<Void>,
  Pointer<Void>,
  Uint32,
  Pointer<_DataBlob>,
);
typedef _CryptProtectDataDart = int Function(
  Pointer<_DataBlob>,
  Pointer<Utf16>,
  Pointer<_DataBlob>,
  Pointer<Void>,
  Pointer<Void>,
  int,
  Pointer<_DataBlob>,
);

typedef _CryptUnprotectDataNative = Int32 Function(
  Pointer<_DataBlob>,
  Pointer<Pointer<Utf16>>,
  Pointer<_DataBlob>,
  Pointer<Void>,
  Pointer<Void>,
  Uint32,
  Pointer<_DataBlob>,
);
typedef _CryptUnprotectDataDart = int Function(
  Pointer<_DataBlob>,
  Pointer<Pointer<Utf16>>,
  Pointer<_DataBlob>,
  Pointer<Void>,
  Pointer<Void>,
  int,
  Pointer<_DataBlob>,
);

typedef _LocalFreeNative = Pointer<Void> Function(Pointer<Void>);
typedef _LocalFreeDart = Pointer<Void> Function(Pointer<Void>);
