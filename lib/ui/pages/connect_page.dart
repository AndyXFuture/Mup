import 'package:flutter/material.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';

import '../../core/app_controller.dart';
import '../components/glass_panel.dart';
import '../theme.dart';

class ConnectPage extends StatefulWidget {
  const ConnectPage({super.key, required this.controller});

  final AppController controller;

  @override
  State<ConnectPage> createState() => _ConnectPageState();
}

class _ConnectPageState extends State<ConnectPage> {
  late final TextEditingController _host =
      TextEditingController(text: widget.controller.draftConfig.host);
  late final TextEditingController _port = TextEditingController(
    text:
        '${widget.controller.draftConfig.port == 0 ? 14040 : widget.controller.draftConfig.port}',
  );
  late final TextEditingController _username =
      TextEditingController(text: widget.controller.draftConfig.username);
  late final TextEditingController _password =
      TextEditingController(text: widget.controller.draftConfig.password);
  late String _protocol = widget.controller.draftConfig.protocol;
  bool _obscure = true;

  @override
  void dispose() {
    _host.dispose();
    _port.dispose();
    _username.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _connect() async {
    FocusScope.of(context).unfocus();
    final port = int.tryParse(_port.text.trim()) ?? 14040;
    await widget.controller.connect(
      _host.text,
      port,
      _username.text,
      _password.text,
      _protocol,
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = MupTheme.of(context);
    final busy = widget.controller.loading;
    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 480),
          child: GlassPanel(
            padding: const EdgeInsets.fromLTRB(30, 28, 30, 28),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Row(
                  children: [
                    SizedBox(
                      width: 42,
                      height: 42,
                      child: ClipRRect(
                        borderRadius: BorderRadius.circular(14),
                        child: Image.asset(
                          'assets/app_icon.png',
                          width: 42,
                          height: 42,
                          fit: BoxFit.cover,
                          filterQuality: FilterQuality.high,
                        ),
                      ),
                    ),
                    const SizedBox(width: 13),
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          '连接音乐服务器',
                          style: TextStyle(
                            color: theme.text,
                            fontSize: 20,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        const SizedBox(height: 3),
                        Text(
                          '通过 Subsonic / OpenSubsonic 接入音桥',
                          style: TextStyle(color: theme.muted, fontSize: 11.5),
                        ),
                      ],
                    ),
                  ],
                ),
                const SizedBox(height: 24),
                Row(
                  children: [
                    Expanded(
                      flex: 3,
                      child: _InputField(
                        label: '服务器地址',
                        hint: 'music.example.com',
                        controller: _host,
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      flex: 2,
                      child: _InputField(
                        label: '端口',
                        hint: '14040',
                        controller: _port,
                        keyboardType: TextInputType.number,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 13),
                _InputField(
                  label: '用户名',
                  hint: '输入用户名',
                  controller: _username,
                ),
                const SizedBox(height: 13),
                _InputField(
                  label: '密码',
                  hint: '输入密码',
                  controller: _password,
                  obscure: _obscure,
                  suffix: IconButton(
                    onPressed: () => setState(() => _obscure = !_obscure),
                    icon: Icon(
                      _obscure ? LucideIcons.eye : LucideIcons.eyeOff,
                      size: 15,
                      color: theme.dim,
                    ),
                  ),
                ),
                const SizedBox(height: 13),
                Row(
                  children: [
                    Text('连接协议',
                        style: TextStyle(color: theme.muted, fontSize: 11.5)),
                    const Spacer(),
                    for (final protocol in const ['http', 'https'])
                      GestureDetector(
                        onTap: () => setState(() => _protocol = protocol),
                        child: AnimatedContainer(
                          duration: const Duration(milliseconds: 170),
                          margin: const EdgeInsets.only(left: 6),
                          padding: const EdgeInsets.symmetric(
                              horizontal: 10, vertical: 6),
                          decoration: BoxDecoration(
                            borderRadius: BorderRadius.circular(8),
                            color: _protocol == protocol
                                ? theme.primary.withValues(alpha: 0.78)
                                : theme.track,
                          ),
                          child: Text(
                            protocol.toUpperCase(),
                            style: TextStyle(
                              color: _protocol == protocol
                                  ? Colors.white
                                  : theme.muted,
                              fontSize: 10,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ),
                      ),
                  ],
                ),
                if (widget.controller.connectError != null) ...[
                  const SizedBox(height: 14),
                  Text(
                    widget.controller.connectError!,
                    style: TextStyle(color: theme.danger, fontSize: 11.5),
                  ),
                ],
                const SizedBox(height: 22),
                SizedBox(
                  height: 42,
                  child: FilledButton(
                    onPressed: busy ? null : _connect,
                    style: FilledButton.styleFrom(
                      backgroundColor: theme.primary,
                      foregroundColor: Colors.white,
                      disabledBackgroundColor:
                          theme.primary.withValues(alpha: 0.44),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(12),
                      ),
                    ),
                    child: busy
                        ? const SizedBox(
                            width: 17,
                            height: 17,
                            child: CircularProgressIndicator(
                              strokeWidth: 1.7,
                              color: Colors.white,
                            ),
                          )
                        : const Text(
                            '连接并进入',
                            style: TextStyle(
                                fontSize: 12.5, fontWeight: FontWeight.w600),
                          ),
                  ),
                ),
                const SizedBox(height: 12),
                Text(
                  '默认端口已设为 14040',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: theme.dim, fontSize: 10.5),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _InputField extends StatelessWidget {
  const _InputField({
    required this.label,
    required this.hint,
    required this.controller,
    this.obscure = false,
    this.keyboardType,
    this.suffix,
  });

  final String label;
  final String hint;
  final TextEditingController controller;
  final bool obscure;
  final TextInputType? keyboardType;
  final Widget? suffix;

  @override
  Widget build(BuildContext context) {
    final theme = MupTheme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: TextStyle(color: theme.muted, fontSize: 11.5),
        ),
        const SizedBox(height: 6),
        Container(
          height: 42,
          decoration: BoxDecoration(
            color: theme.track,
            borderRadius: BorderRadius.circular(11),
            border: Border.all(color: theme.rimSoft),
          ),
          child: TextField(
            controller: controller,
            obscureText: obscure,
            keyboardType: keyboardType,
            maxLines: 1,
            style: TextStyle(color: theme.text, fontSize: 12.5),
            cursorColor: theme.primaryLight,
            decoration: InputDecoration(
              border: InputBorder.none,
              isDense: true,
              hintText: hint,
              hintStyle: TextStyle(color: theme.dim, fontSize: 12),
              contentPadding:
                  const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
              suffixIcon: suffix,
            ),
          ),
        ),
      ],
    );
  }
}
