import 'package:flutter/material.dart';
import '../uikit/colors.dart';
import '../uikit/custom_header.dart';

// Экран Опросы
class SurveysScreen extends StatelessWidget {
  const SurveysScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: background,
      body: SafeArea(
        child: Column(
          children: [
            CustomHeader(title: 'Опросы', onClose: () {}, onMenu: () {}),
            const Expanded(child: Center(child: Text('Экран в разработке'))),
          ],
        ),
      ),
    );
  }
}
