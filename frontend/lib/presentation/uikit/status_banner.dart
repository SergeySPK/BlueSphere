import 'package:flutter/material.dart';
import 'package:vize/vize.dart';
import 'colors.dart';

// Кастомный баннер для отображения уровня нагрузки класса
class StatusBanner extends StatelessWidget {
  final int level; // Уровень нагрузки
  final String date; // Дата опроса для подписи
  final bool showButton; // Показывать ли кнопку перехода к сводке
  final VoidCallback? onGoToSummary; // Колбэк для кнопки

  const StatusBanner({super.key, required this.level, required this.date, this.showButton = true, this.onGoToSummary});

  @override
  Widget build(BuildContext context) {
    Color cardColor;
    IconData icon;
    String title;
    String description;

    // Настраиваем цвета, иконки и текст в зависимости от уровня нагрузки
    switch (level) {
      case 0:
        cardColor = loadMax;
        icon = Icons.keyboard_double_arrow_up;
        title = 'ЧРЕЗМЕРНАЯ НАГРУЗКА';
        description = 'Необходимо внести изменения в расписание';
        break;
      case 1:
        cardColor = loadHigh;
        icon = Icons.keyboard_arrow_up;
        title = 'ВЫСОКАЯ НАГРУЗКА';
        description = 'Чуть выше нормы. Рекомендуем внести изменения';
        break;
      case 2:
        cardColor = loadMedium;
        icon = Icons.remove;
        title = 'СРЕДНЯЯ НАГРУЗКА';
        description = 'Допустимая норма';
        break;
      case 3:
        cardColor = loadLow;
        icon = Icons.keyboard_arrow_down;
        title = 'НЕБОЛЬШАЯ НАГРУЗКА';
        description = 'Допустимый разгрузочный день.\nОтдых для учащихся пойдет на пользу';
        break;
      case 4:
      default:
        cardColor = loadMin;
        icon = Icons.keyboard_double_arrow_down;
        title = 'МИНИМАЛЬНАЯ НАГРУЗКА';
        description = 'Хорошо подойдет для назначения работы';
        break;
    }

    return Container(
      padding: pa(10),
      decoration: BoxDecoration(color: white, borderRadius: BorderRadius.circular(12)),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Container(
            width: 79.fw,
            height: 79.fh,
            decoration: BoxDecoration(
              color: Colors.transparent,
              shape: BoxShape.circle,
              border: Border.all(color: cardColor, width: 4.fw),
            ),
            child: Center(
              child: Icon(icon, color: cardColor, size: 50.fh),
            ),
          ),
          SizedBox(width: 12.fw),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'общая оценка состояния учащихся на $date',
                  style: TextStyle(fontFamily: 'Inter', fontSize: 8.fh, fontWeight: .w400, color: text),
                ),
                SizedBox(height: 4.fh),
                Text(
                  title,
                  style: TextStyle(fontFamily: 'Inter', fontSize: 14.fh, fontWeight: .w600, color: cardColor),
                ),
                Text(
                  description,
                  style: TextStyle(fontFamily: 'SF Pro', fontSize: 10.fh, fontWeight: .w400, color: cardColor),
                ),
                if (showButton) ...[
                  SizedBox(height: 15.fh),
                  SizedBox(
                    height: 21.fh,
                    child: ElevatedButton(
                      onPressed: onGoToSummary,
                      style: ElevatedButton.styleFrom(
                        backgroundColor: cardColor,
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(4)),
                      ),
                      child: Text(
                        'Перейти к сводке',
                        style: TextStyle(fontFamily: 'SF Pro', fontSize: 10.fh, color: white, fontWeight: .w500),
                      ),
                    ),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}
