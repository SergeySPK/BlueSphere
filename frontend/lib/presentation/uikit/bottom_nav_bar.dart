import 'package:flutter/material.dart';
import 'package:vize/vize.dart';
import 'colors.dart';

// Кастомная нижняя панель навигации
class BottomNavBar extends StatelessWidget {
  final int currentIndex;
  final Function(int) onTap;
  final bool isTeacher;

  const BottomNavBar({super.key, required this.currentIndex, required this.onTap, required this.isTeacher});

  @override
  Widget build(BuildContext context) {
    final List<BottomNavigationBarItem> items = [];

    if (isTeacher) {
      items.add(_buildItem('assets/school.png', 'Классы'));
    }

    items.add(_buildItem('assets/file.png', 'Нагрузка'));
    items.add(_buildItem('assets/chat.png', 'Опросы'));

    return Container(
      color: background,
      child: Theme(
        data: Theme.of(context).copyWith(splashColor: Colors.transparent, highlightColor: Colors.transparent, hoverColor: Colors.transparent),
        child: BottomNavigationBar(
          currentIndex: currentIndex,
          onTap: onTap,
          backgroundColor: Colors.transparent,
          type: BottomNavigationBarType.fixed,
          elevation: 0,
          selectedFontSize: 10,
          unselectedFontSize: 10,
          selectedItemColor: bottomBarText,
          unselectedItemColor: text,
          selectedLabelStyle: TextStyle(fontFamily: 'SF Pro', fontWeight: FontWeight.w500, letterSpacing: 0.12),
          unselectedLabelStyle: TextStyle(fontFamily: 'SF Pro', fontWeight: FontWeight.w500, letterSpacing: 0.12),
          items: items,
        ),
      ),
    );
  }

  BottomNavigationBarItem _buildItem(String iconPath, String label) {
    return BottomNavigationBarItem(
      icon: Padding(
        padding: po(t: 5, b: 3),
        child: Image.asset(iconPath, width: 24.fw, height: 24.fh, color: text),
      ),
      activeIcon: Padding(
        padding: po(t: 5, b: 3),
        child: Image.asset(iconPath, width: 24.fw, height: 24.fh, color: bottomBarText),
      ),
      label: label,
    );
  }
}
