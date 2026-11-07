import 'package:flutter/material.dart';
import 'package:vize/vize.dart';
import 'colors.dart';

// Кастомная верхняя шапка
class CustomHeader extends StatelessWidget {
  final String title; // Текст заголовка

  const CustomHeader({super.key, required this.title});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: ps(h: 14.fw, v: 11.fh),
      child: Center(
        child: Container(
          padding: ps(h: 16.fw, v: 6.fh),
          decoration: BoxDecoration(color: white, borderRadius: BorderRadius.circular(12)),
          child: Text(
            title,
            style: TextStyle(fontFamily: 'SF Pro', fontSize: 15.fh, fontWeight: .w600, color: classColor),
          ),
        ),
      ),
    );
  }
}
