import 'package:flutter/material.dart';
import 'package:vize/vize.dart';
import '../uikit/custom_header.dart';
import '../data/mock_data.dart';
import '../models/school_class.dart';
import '../uikit/colors.dart';

// Экран Классы
class ClassesScreen extends StatefulWidget {
  final Function(String) onClassSelected;

  const ClassesScreen({super.key, required this.onClassSelected});

  @override
  State<ClassesScreen> createState() => _ClassesScreenState();
}

class _ClassesScreenState extends State<ClassesScreen> {
  String? _expandedGroup;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: background,
      body: SafeArea(
        child: Column(
          children: [
            CustomHeader(title: 'Выберите класс', onClose: () {}, onMenu: () {}),
            Expanded(
              child: ListView.builder(
                padding: po(l: 16, r: 16, t: 8, b: 80),
                itemCount: mockClasses.length,
                itemBuilder: (context, index) {
                  final groupName = mockClasses.keys.elementAt(index);
                  final classes = mockClasses[groupName]!;
                  return _buildAccordionGroup(groupName, classes);
                },
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildAccordionGroup(String groupName, List<SchoolClass> classes) {
    bool isExpanded = _expandedGroup == groupName;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        GestureDetector(
          onTap: () {
            setState(() {
              _expandedGroup = isExpanded ? null : groupName;
            });
          },
          child: Padding(
            padding: po(t: 16, b: 12),
            child: Row(
              children: [
                Text(
                  groupName,
                  style: TextStyle(fontFamily: 'Inter', fontSize: 18, fontWeight: .w600, color: classColor),
                ),
                Spacer(),
                Image.asset(isExpanded ? 'assets/up.png' : 'assets/down.png', width: 14.fw, height: 7.fh, color: classColor),
              ],
            ),
          ),
        ),

        if (isExpanded)
          Padding(
            padding: po(t: 4, b: 16),
            child: Wrap(
              spacing: 8.fw,
              runSpacing: 8.fh,
              children: classes.map((schoolClass) {
                return _buildClassChip(schoolClass);
              }).toList(),
            ),
          ),

        Divider(color: text.withOpacity(0.2), thickness: 1, height: 1),
      ],
    );
  }

  Widget _buildClassChip(SchoolClass schoolClass) {
    return GestureDetector(
      onTap: () {
        widget.onClassSelected(schoolClass.name);
      },
      child: Container(
        padding: ps(v: 6, h: 18),
        decoration: BoxDecoration(color: white, borderRadius: BorderRadius.circular(12)),
        child: Text(
          schoolClass.name,
          style: TextStyle(fontFamily: 'Inter', fontSize: 14, fontWeight: .w600, color: classColor),
        ),
      ),
    );
  }
}
