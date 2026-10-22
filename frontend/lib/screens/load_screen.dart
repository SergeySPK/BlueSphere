import 'package:flutter/material.dart';
import 'package:vize/vize.dart';
import '../uikit/colors.dart';
import '../uikit/custom_header.dart';
import '../uikit/status_banner.dart';
import '../uikit/calendar.dart';
import '../uikit/recommendations_block.dart';
import '../data/mock_data.dart';

// Экран нагрузки
class LoadScreen extends StatefulWidget {
  final String className;
  final VoidCallback onGoToClasses;

  const LoadScreen({super.key, required this.className, required this.onGoToClasses});

  @override
  State<LoadScreen> createState() => _LoadScreenState();
}

class _LoadScreenState extends State<LoadScreen> {
  @override
  Widget build(BuildContext context) {
    final bool isClassSelected = widget.className != 'Выберите класс';

    return Scaffold(
      backgroundColor: background,
      body: SafeArea(
        child: Column(
          children: [
            // Шапка с крестиком и троеточием
            CustomHeader(title: isClassSelected ? widget.className : 'Нагрузка', onClose: widget.onGoToClasses, onMenu: () {}),

            // Основной контент
            Expanded(
              child: !isClassSelected
                  ? _buildNoClassSelected()
                  : SingleChildScrollView(
                      padding: po(t: 8, l: 16, r: 16, b: 80),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          // 1. Баннер с итогами опроса
                          StatusBanner(level: mockClassStatus.level, date: mockClassStatus.date),
                          SizedBox(height: 16.fh),

                          // 2. Календарь (Тепловая карта)
                          LoadCalendar(
                            date: DateTime.now(), // Передаем текущий месяц
                            loadDays: mockLoadDays,
                          ),
                          SizedBox(height: 16.fh),

                          // 3. Блок рекомендаций из UI-кита
                          RecommendationsBlock(daysToReduce: mockRecommendation.daysToReduce, daysToMoveTo: mockRecommendation.daysToMoveTo),
                        ],
                      ),
                    ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildNoClassSelected() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Text(
            'Класс не выбран',
            style: TextStyle(fontFamily: 'Inter', fontSize: 18, fontWeight: FontWeight.w600, color: black),
          ),
          SizedBox(height: 8.fh),
          Text(
            'Чтобы посмотреть нагрузку,\nвыберите класс',
            textAlign: TextAlign.center,
            style: TextStyle(fontFamily: 'SF Pro', fontSize: 14, fontWeight: FontWeight.w400, color: text),
          ),
          SizedBox(height: 24.fh),
          ElevatedButton(
            onPressed: widget.onGoToClasses,
            style: ElevatedButton.styleFrom(
              backgroundColor: bottomBarText,
              padding: po(l: 24, r: 24, t: 12, b: 12),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            ),
            child: Text(
              'Перейти к классам',
              style: TextStyle(fontFamily: 'Inter', fontSize: 14, fontWeight: FontWeight.w500, color: white),
            ),
          ),
        ],
      ),
    );
  }
}
