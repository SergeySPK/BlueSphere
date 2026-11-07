import 'dart:async';
import 'package:flutter/material.dart';
import 'package:vize/vize.dart';
import '../uikit/colors.dart';

// Начальный экран загрузки
class SplashScreen extends StatefulWidget {
  const SplashScreen({super.key});

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen> {
  final List<String> _phrases = [
    'Не забываем голову...',
    'Просим преподавателя не ставить вам контрольную...',
    'Выходим и заходим нормально...',
    'Просим выполнить домашку...',
    'Вызываем родителей в школу...',
    'Рассказываем смешную шутку...',
  ];

  int _currentIndex = 0;
  late Timer _timer;
  bool _isVisible = true;

  @override
  void initState() {
    super.initState();

    _timer = Timer.periodic(const Duration(milliseconds: 2500), (timer) {
      if (!mounted) return;
      setState(() => _isVisible = false);

      Future.delayed(const Duration(milliseconds: 300), () {
        if (!mounted) return;
        setState(() {
          _currentIndex = (_currentIndex + 1) % _phrases.length;
          _isVisible = true;
        });
      });
    });
  }

  @override
  void dispose() {
    _timer.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: background,
      body: SafeArea(
        child: Stack(
          children: [
            Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Image.asset('assets/logo.png', width: 100.fw, height: 100.fh),
                  SizedBox(height: 10.fh),
                  Text(
                    'Планировщик\nучебной нагрузки',
                    textAlign: TextAlign.center,
                    style: TextStyle(fontFamily: 'SF Pro', fontSize: 20.fh, fontWeight: .w700, color: loadMax, height: 1.2),
                  ),
                  SizedBox(height: 24.fh),
                  SizedBox(
                    width: 250.fw,
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(10.r),
                      child: LinearProgressIndicator(minHeight: 9, backgroundColor: results, valueColor: AlwaysStoppedAnimation<Color>(loadMax)),
                    ),
                  ),
                  SizedBox(height: 12.fh),
                  AnimatedOpacity(
                    opacity: _isVisible ? 1.0 : 0.0,
                    duration: const Duration(milliseconds: 300),
                    child: Text(
                      _phrases[_currentIndex],
                      textAlign: TextAlign.center,
                      style: TextStyle(fontFamily: 'SF Pro', fontSize: 10.fh, color: grey, fontWeight: .w500),
                    ),
                  ),
                ],
              ),
            ),

            Positioned(
              bottom: 24.fh,
              left: 0,
              right: 0,
              child: Text(
                'v.0.0.1',
                textAlign: TextAlign.center,
                style: TextStyle(fontFamily: 'SF Pro', fontSize: 10.fh, color: text, fontWeight: .w600),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
