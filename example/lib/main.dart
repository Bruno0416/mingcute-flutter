import 'package:flutter/material.dart';
import 'package:mingcute_icons/mingcute_icons.dart';

void main() => runApp(const MaterialApp(home: ExampleScreen()));

class ExampleScreen extends StatelessWidget {
  const ExampleScreen({super.key});
  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('MingCute Icons')),
        body: Center(
          child: Wrap(spacing: 24, children: [
            Icon(MingCute.regular.home_1, size: 36),
            Icon(MingCute.regular.search_2, size: 36),
            Icon(MingCute.filled.heart, size: 36),
            Icon(MingCute.filled.star, size: 36),
          ]),
        ),
      );
}
