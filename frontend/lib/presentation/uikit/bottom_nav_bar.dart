import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:vize/vize.dart';
import 'colors.dart';

// Кастомная нижняя панель навигации
class BottomNavBar extends StatelessWidget {
  final int currentIndex; // Индекс текущей активной вкладки
  final Function(int) onTap; // Колбэк для обработки нажатий на вкладки
  final bool isTeacher; // Показывать ли вкладку "Классы"

  const BottomNavBar({super.key, required this.currentIndex, required this.onTap, required this.isTeacher});

  @override
  Widget build(BuildContext context) {
    final List<BottomNavigationBarItem> items = [];

    // Учителям и админам добавляем вкладку "Классы"
    if (isTeacher) {
      items.add(_buildItem('assets/school.svg', 'Классы'));
    }

    items.add(_buildItem('assets/file.svg', 'Нагрузка'));
    items.add(_buildItem('assets/chat.svg', 'Опросы'));

    return Container(
      color: background,
      padding: po(b: 15.fh),
      child: Theme(
        data: Theme.of(context).copyWith(splashColor: Colors.transparent, highlightColor: Colors.transparent, hoverColor: Colors.transparent),
        child: BottomNavigationBar(
          currentIndex: currentIndex,
          onTap: onTap,
          backgroundColor: Colors.transparent,
          type: BottomNavigationBarType.fixed,
          elevation: 0,
          selectedFontSize: 10.fh,
          unselectedFontSize: 10.fh,
          selectedItemColor: bottomBarText,
          unselectedItemColor: text,
          selectedLabelStyle: TextStyle(fontFamily: 'SF Pro', fontWeight: .w500, letterSpacing: 0.12),
          unselectedLabelStyle: TextStyle(fontFamily: 'SF Pro', fontWeight: .w500, letterSpacing: 0.12),
          items: items,
        ),
      ),
    );
  }

  // Вспомогательный метод для создания элемента панели с SVG-иконкой
  BottomNavigationBarItem _buildItem(String iconPath, String label) {
    return BottomNavigationBarItem(
      icon: SvgPicture.asset(iconPath, width: 24.fw, height: 24.fh, colorFilter: ColorFilter.mode(text, BlendMode.srcIn)),
      activeIcon: SvgPicture.asset(iconPath, width: 24.fw, height: 24.fh, colorFilter: ColorFilter.mode(bottomBarText, BlendMode.srcIn)),
      label: label,
    );
  }
}
