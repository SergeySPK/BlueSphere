import 'package:flutter/material.dart';
import 'package:vize/vize.dart';
import 'colors.dart';

// Кастомная верхняя панель
class CustomHeader extends StatelessWidget {
  final String title;
  final VoidCallback onClose;
  final VoidCallback onMenu;

  const CustomHeader({super.key, required this.title, required this.onClose, required this.onMenu});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: po(l: 14, r: 14, t: 13, b: 11),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Container(
            width: 30.fw,
            height: 30.fh,
            decoration: BoxDecoration(color: white, shape: BoxShape.circle),
            child: IconButton(
              icon: Image.asset('assets/exit.png', width: 12.5.fw, height: 12.5.fh),
              onPressed: onClose,
            ),
          ),
          Container(
            padding: ps(h: 18, v: 6),
            decoration: BoxDecoration(color: white, borderRadius: BorderRadius.circular(12.r)),
            child: Text(
              title,
              style: TextStyle(fontFamily: 'SF Pro', fontSize: 16, fontWeight: .w600, color: classColor),
            ),
          ),
          Container(
            width: 30.fw,
            height: 30.fh,
            decoration: BoxDecoration(color: white, shape: BoxShape.circle),
            child: IconButton(
              icon: Image.asset('assets/menu.png', width: 24.fw, height: 24.fh),
              onPressed: onMenu,
            ),
          ),
        ],
      ),
    );
  }
}
