import 'package:flutter/material.dart';
import 'package:vize/vize.dart';
import '../../domain/school_class.dart';
import '../../data/api_service.dart';
import '../uikit/colors.dart';
import '../uikit/custom_header.dart';
import '../uikit/error_screen.dart';

class ClassesScreen extends StatefulWidget {
  final Function(String id, String name) onClassSelected;

  const ClassesScreen({super.key, required this.onClassSelected});

  @override
  State<ClassesScreen> createState() => _ClassesScreenState();
}

class _ClassesScreenState extends State<ClassesScreen> {
  Map<String, List<SchoolClass>>? _classes;
  bool _isLoading = true;
  String? _expandedGroup;
  int? _errorCode;
  List<String> _sortedGroupNames = [];

  @override
  void initState() {
    super.initState();
    _loadClasses();
  }

  Future<void> _loadClasses() async {
    setState(() {
      _isLoading = true;
      _errorCode = null;
    });

    try {
      final data = await ApiService.getClasses();
      if (mounted) {
        setState(() {
          _classes = data;
          _sortedGroupNames = _classes!.keys.toList()
            ..sort((a, b) {
              final gradeA = int.tryParse(a.split(' ').first) ?? 0;
              final gradeB = int.tryParse(b.split(' ').first) ?? 0;
              return gradeA.compareTo(gradeB);
            });
          _isLoading = false;
        });
      }
    } catch (e) {
      int code = 500;
      final errorString = e.toString();
      if (errorString.contains('Exception: ')) {
        code = int.tryParse(errorString.split('Exception: ')[1]) ?? 500;
      }

      if (mounted) {
        setState(() {
          _errorCode = code;
          _isLoading = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: background,
      body: Column(
        children: [
          CustomHeader(title: 'Выберите класс', onClose: () {}, onMenu: () {}),
          Expanded(
            child: _errorCode != null
                ? ErrorScreen(code: _errorCode!)
                : _isLoading
                ? Center(child: CircularProgressIndicator())
                : _classes == null
                ? Center(child: Text('Ошибка загрузки'))
                : ListView.builder(
                    padding: po(l: 16, r: 16),
                    itemCount: _sortedGroupNames.length,
                    itemBuilder: (context, index) {
                      final groupName = _sortedGroupNames[index];
                      final classes = _classes![groupName]!;
                      return _buildAccordionGroup(groupName, classes);
                    },
                  ),
          ),
        ],
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
                  style: TextStyle(fontFamily: 'Inter', fontSize: 18, fontWeight: .w600, color: black),
                ),
                Spacer(),
                Image.asset(isExpanded ? 'assets/up.png' : 'assets/down.png', width: 24, height: 24),
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
        widget.onClassSelected(schoolClass.id, schoolClass.name);
      },
      child: Container(
        padding: po(l: 16, r: 16, t: 8, b: 8),
        decoration: BoxDecoration(color: white, borderRadius: BorderRadius.circular(20)),
        child: Text(
          schoolClass.name,
          style: TextStyle(fontFamily: 'Inter', fontSize: 14, fontWeight: .w400, color: black),
        ),
      ),
    );
  }
}
