import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/material.dart';
import 'package:vize/vize.dart';
import 'package:blue_sphere/presentation/screens/splash_screen.dart';

void main() {
  // Для MVP реализован один базовый тест (Smoke-тест)
  testWidgets('SplashScreen успешно создается', (WidgetTester tester) async {
    await tester.pumpWidget(
      MaterialApp(
        builder: (context, child) {
          Vize.init(context, figmaWidth: 375, figmaHeight: 812);
          return child!;
        },
        home: const SplashScreen(),
      ),
    );
    await tester.pump(const Duration(milliseconds: 500));
    expect(find.byType(SplashScreen), findsOneWidget);
  });
}
