import 'package:flutter/material.dart';
import 'package:vize/vize.dart';
import 'colors.dart';

// Кастомная верхняя шапка
class CustomHeader extends StatelessWidget {
  final String title;
  final bool showBack;
  final VoidCallback? onBack;
  final bool showMenu;
  final VoidCallback? onMenu;

  const CustomHeader({super.key, required this.title, this.showBack = false, this.onBack, this.showMenu = false, this.onMenu});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: ps(h: 14.fw, v: 11.fh),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          if (showBack)
            GestureDetector(
              onTap: onBack,
              child: Container(
                width: 30.fw,
                height: 30.fh,
                decoration: BoxDecoration(color: white, shape: BoxShape.circle),
                child: Center(
                  child: Icon(Icons.arrow_back_ios_new, color: grey, size: 16.fh),
                ),
              ),
            )
          else
            SizedBox(width: 30.fw, height: 30.fh),
          Container(
            padding: ps(h: 26.fw, v: 6.fh),
            decoration: BoxDecoration(color: white, borderRadius: BorderRadius.circular(12)),
            child: Text(
              title,
              style: TextStyle(fontFamily: 'SF Pro', fontSize: 15.fh, fontWeight: .w600, color: classColor),
            ),
          ),

          if (showMenu)
            GestureDetector(
              onTap: onMenu,
              child: Container(
                width: 30.fw,
                height: 30.fh,
                decoration: BoxDecoration(color: white, shape: BoxShape.circle),
                child: Center(
                  child: Icon(Icons.more_vert, color: grey, size: 20.fw),
                ),
              ),
            )
          else
            SizedBox(width: 30.fw, height: 30.fh),
        ],
      ),
    );
  }
}
