import 'package:flutter/material.dart';
import 'package:vize/vize.dart';
import 'colors.dart';

// Кастомная нижняя панель навигации
class BottomNavBar extends StatelessWidget {
  final int currentIndex;
  final Function(int) onTap;

  const BottomNavBar({super.key, required this.currentIndex, required this.onTap});

  @override
  Widget build(BuildContext context) {
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
          items: [_buildItem('assets/school.png', 'Классы'), _buildItem('assets/file.png', 'Нагрузка'), _buildItem('assets/chat.png', 'Опросы'), _buildItem('assets/settings.png', 'Настройки')],
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
