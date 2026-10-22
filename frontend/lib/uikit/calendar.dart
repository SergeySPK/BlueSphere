import 'package:flutter/material.dart';
import 'package:vize/vize.dart';
import '../models/load_day.dart';
import 'colors.dart';

// Кастомный календарь
class LoadCalendar extends StatelessWidget {
  final DateTime date; // Какой месяц мы рисуем
  final List<LoadDay> loadDays; // Мок данные

  const LoadCalendar({super.key, required this.date, required this.loadDays});

  Color _getLoadColor(int level) {
    switch (level) {
      case 0:
        return loadMax;
      case 1:
        return loadHigh;
      case 2:
        return loadMedium;
      case 3:
        return loadLow;
      default:
        return loadMin;
    }
  }

  String _getMonthName(int month) {
    const months = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'];
    return months[month - 1];
  }

  @override
  Widget build(BuildContext context) {
    final now = DateTime.now();
    final int daysInMonth = DateTime(date.year, date.month + 1, 0).day;
    final int firstDayWeekday = DateTime(date.year, date.month, 1).weekday;

    List<Widget> gridCells = [];

    for (int i = 1; i < firstDayWeekday; i++) {
      gridCells.add(_buildEmptyStartCell());
    }

    int currentWeekday = firstDayWeekday;

    for (int day = 1; day <= daysInMonth; day++) {
      final dayData = loadDays.firstWhere((d) => d.day == day, orElse: () => LoadDay(day: day, level: 4));

      final bool isToday = (date.year == now.year) && (date.month == now.month) && (day == now.day);

      if (currentWeekday == 7) {
        gridCells.add(_buildSundayCell(day, isToday));
        currentWeekday = 1;
      } else {
        gridCells.add(_buildDayCell(dayData, isToday));
        currentWeekday++;
      }
    }

    while (gridCells.length % 7 != 0) {
      gridCells.add(_buildEmptyStartCell());
    }

    return Container(
      padding: pa(16),
      decoration: BoxDecoration(color: white, borderRadius: BorderRadius.circular(12)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    _getMonthName(date.month).toUpperCase(),
                    style: TextStyle(fontFamily: 'SF Pro', fontSize: 15, fontWeight: .w700, color: loadMax),
                  ),
                  Text(
                    'карта нагрузки',
                    style: TextStyle(fontFamily: 'SF Pro', fontSize: 11, fontWeight: .w400, color: text),
                  ),
                ],
              ),
              Spacer(),
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _buildLegendItem('чрезмерная нагрузка', loadMax),
                  SizedBox(height: 6.fh),
                  _buildLegendItem('высокая нагрузка', loadHigh),
                ],
              ),
              SizedBox(width: 11.fw),
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _buildLegendItem('средняя нагрузка', loadMedium),
                  SizedBox(height: 6.fh),
                  _buildLegendItem('небольшая нагрузка', loadLow),
                  SizedBox(height: 6.fh),
                  _buildLegendItem('минимальная нагрузка', loadMin),
                ],
              ),
            ],
          ),
          SizedBox(height: 20.fh),
          GridView.builder(
            shrinkWrap: true,
            physics: NeverScrollableScrollPhysics(),
            gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(crossAxisCount: 7, mainAxisSpacing: 8.fh, crossAxisSpacing: 8.fw, childAspectRatio: 1),
            itemCount: gridCells.length,
            itemBuilder: (context, index) {
              return gridCells[index];
            },
          ),
          SizedBox(height: 8.fh),
          Row(mainAxisAlignment: MainAxisAlignment.spaceAround, children: [_buildWeekDay('пн'), _buildWeekDay('вт'), _buildWeekDay('ср'), _buildWeekDay('чт'), _buildWeekDay('пт'), _buildWeekDay('сб'), _buildWeekDay('вс')]),
        ],
      ),
    );
  }

  Widget _buildEmptyStartCell() {
    return Container(
      decoration: BoxDecoration(color: Colors.transparent, borderRadius: BorderRadius.circular(5)),
    );
  }

  Widget _buildDayCell(LoadDay dayData, bool isToday) {
    final level = dayData.level;
    return Container(
      decoration: BoxDecoration(
        color: _getLoadColor(level),
        borderRadius: BorderRadius.circular(5),
        border: isToday ? Border.all(color: currentDayBorder, width: 3) : null,
      ),
      child: Center(
        child: Text(
          '${dayData.day}',
          style: TextStyle(fontFamily: 'Inter', fontSize: 12, fontWeight: .w400, color: white),
        ),
      ),
    );
  }

  Widget _buildSundayCell(int day, bool isToday) {
    return Container(
      decoration: BoxDecoration(
        color: emptyCell,
        borderRadius: BorderRadius.circular(5),
        border: isToday ? Border.all(color: currentDayBorder, width: 3) : null,
      ),
      child: Center(
        child: Text(
          '$day',
          style: TextStyle(fontFamily: 'Inter', fontSize: 12, fontWeight: .w400, color: text),
        ),
      ),
    );
  }

  Widget _buildLegendItem(String title, Color color) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 8,
          height: 8,
          decoration: BoxDecoration(color: color, shape: BoxShape.circle),
        ),
        SizedBox(width: 4.fw),
        Text(
          title,
          style: TextStyle(fontFamily: 'SF Pro', fontSize: 7, fontWeight: .w400, color: black),
        ),
      ],
    );
  }

  Widget _buildWeekDay(String day) {
    return Text(
      day,
      style: TextStyle(fontFamily: 'SF Pro', fontSize: 11, fontWeight: .w400, color: text),
    );
  }
}
