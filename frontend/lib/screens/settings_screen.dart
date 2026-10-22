import 'package:flutter/material.dart';
import '../uikit/colors.dart';
import '../uikit/custom_header.dart';

// Экран под вопросом
class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: background,
      body: SafeArea(
        child: Column(
          children: [
            CustomHeader(title: 'Настройки', onClose: () {}, onMenu: () {}),
            const Expanded(child: Center(child: Text('Экран в разработке'))),
          ],
        ),
      ),
    );
  }
}
