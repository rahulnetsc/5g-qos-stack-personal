.
├── amf-logs.log
├── data_recording.md
├── design-doc.md
├── gnb.log
├── ia_p5g_oai_reading_notes.md
├── installation-instructions.md
├── NR_SA_Tutorial_OAI_CN5G.md
├── NR_SA_Tutorial_OAI_multi_UE.md
├── NR_SA_Tutorial_OAI_nrUE.md
├── oai-benchmark
│   ├── collect
│   │   └── t_tracer_collector.py
│   ├── config
│   │   ├── core
│   │   ├── gnb
│   │   │   └── gnb.sa.band78.106prb.rfsim.conf
│   │   └── ue
│   │       └── ue_smoke.conf
│   ├── results
│   └── scripts
│       ├── debug_datapath.sh
│       ├── env.sh
│       ├── lib.sh
│       ├── nrL1_UE_stats-0.log
│       ├── scripts-results.log
│       ├── verify_stack.log
│       ├── verify_stack-log.log
│       ├── verify_stack.sh
│       ├── verify_stack_stage1.log
│       ├── verify_stack_stage2.log
│       └── verify_stack_stage4.log
├── oai-file-structure.md
├── oai-file-tree.md
├── openairinterface5g
│   ├── build_final.log
│   ├── build_ttracer.log
│   ├── CHANGELOG.md
│   ├── charts
│   │   ├── physims-4g
│   │   │   ├── charts
│   │   │   ├── Chart.yaml
│   │   │   ├── templates
│   │   │   └── values.yaml
│   │   └── physims-5g
│   │       ├── charts
│   │       ├── Chart.yaml
│   │       ├── templates
│   │       └── values.yaml
│   ├── ci-scripts
│   │   ├── args_parse.py
│   │   ├── as_ue
│   │   │   ├── aw2s-asue.cfg
│   │   │   ├── aw2s-multi-00102-20.cfg
│   │   │   ├── aw2s-multi-00102-2x2-v2.cfg
│   │   │   ├── config.cfg
│   │   │   ├── multi-00105-100.cfg
│   │   │   └── multi-00105-40.cfg
│   │   ├── attenuatorctl.py
│   │   ├── checkAddedWarnings.sh
│   │   ├── checkCodingFormattingRules.sh
│   │   ├── checkGitLabMergeRequestLabels.sh
│   │   ├── ci_ctl_adb.sh
│   │   ├── ci_ctl_qtel.py
│   │   ├── ci_infra.yaml
│   │   ├── cls_analysis.py
│   │   ├── cls_ci_helper.py
│   │   ├── cls_cluster.py
│   │   ├── cls_cmd.py
│   │   ├── cls_containerize.py
│   │   ├── cls_corenetwork.py
│   │   ├── cls_loganalysis.py
│   │   ├── cls_module.py
│   │   ├── cls_native.py
│   │   ├── cls_oaicitest.py
│   │   ├── cls_oai_html.py
│   │   ├── cls_static_code_analysis.py
│   │   ├── colosseum_scripts
│   │   │   ├── check-results.sh
│   │   │   ├── get-test-results.sh
│   │   │   ├── launch-job.sh
│   │   │   ├── README.md
│   │   │   ├── set-job-status.sh
│   │   │   └── wait-job-end.sh
│   │   ├── conf_files
│   │   │   ├── channelmod_rfsimu.conf
│   │   │   ├── enb.band38.25prb.rfsim.conf
│   │   │   ├── enb.band38.lte_2x2.100prb.usrpn310.conf
│   │   │   ├── enb.band38.lte_2x2_tm2.100prb.usrpn310.conf
│   │   │   ├── enb.band40.100prb.usrpb200.tm1-defaultscheduler.conf
│   │   │   ├── enb.band40.25prb.usrpb200.conf
│   │   │   ├── enb.band7.100prb.rfsim.conf
│   │   │   ├── enb.band7.100prb.usrpb200.tm1.conf
│   │   │   ├── enb.band7.25prb.l2sim.conf
│   │   │   ├── enb.band7.25prb.rfsim.conf
│   │   │   ├── enb.band7.25prb.rfsim.nos1.conf
│   │   │   ├── enb.band7.25prb.usrpb200.conf
│   │   │   ├── enb.band7.25prb.usrpb200.tm1.conf
│   │   │   ├── enb.band7.25prb.usrpb200.tm1-norrc.conf
│   │   │   ├── enb.band7.50prb.rfsim.conf
│   │   │   ├── enb.band7.50prb.usrpb200.tm1.conf
│   │   │   ├── enb.band7.tm1.25prb.rfsim.mbms.conf
│   │   │   ├── enb.nsa.band7.25prb.usrpb200.conf
│   │   │   ├── enb-rcc.band40.25prb.tm1.if4p5.fair-scheduler.conf
│   │   │   ├── enb-rcc.band7.25prb.tm1.if4p5.conf
│   │   │   ├── enb-rru.band40.usrpb210.tm1.conf
│   │   │   ├── enb-rru.band7.usrpb210.tm1.conf
│   │   │   ├── gnb.band66.106prb.rfsim.phytest-dora.conf
│   │   │   ├── gnb.band77.273prb.fhi72.4x4-vvdn-phytest.conf
│   │   │   ├── gnb.band78.106prb.rfsim.phytest-dora.conf
│   │   │   ├── gnb.band79.106prb.usrpn300.phytest-dora.conf
│   │   │   ├── gnb.band79.162prb.usrpn300.phytest-dora.conf
│   │   │   ├── gnb.band79.273prb.usrpn300.phytest-dora.conf
│   │   │   ├── gnb-cucp.sa.e1-ho-n2.conf
│   │   │   ├── gnb-cucp.sa.f1.conf
│   │   │   ├── gnb-cucp.sa.f1.quectel.conf
│   │   │   ├── gnb-cu.sa.band78.106prb.conf
│   │   │   ├── gnb-cu.sa.f1.conf
│   │   │   ├── gnb-cu.sa.f1.ho.conf
│   │   │   ├── gnb-cuup.sa.f1.conf
│   │   │   ├── gnb-cuup.sa.f1.quectel.conf
│   │   │   ├── gnb-du.sa.band1.52prb.usrpb210.conf
│   │   │   ├── gnb-du.sa.band77.273prb.fhi72.4x4-4L-vvdn.conf
│   │   │   ├── gnb-du.sa.band78.106prb.rfsim.conf
│   │   │   ├── gnb-du.sa.band78.106prb.usrpb200.conf
│   │   │   ├── gnb-du.sa.band78.273prb.fhi72.4x4-4L-benetel550.conf
│   │   │   ├── gnb-du.sa.band78.273prb.fhi72.4x4-4L-liteon.conf
│   │   │   ├── gnb-du.sa.band78.273prb.fhi72.4x4-4L-metanoia.conf
│   │   │   ├── gnb-du.sa.band78.273prb.fhi72.8x8-benetel650_650.conf
│   │   │   ├── gnb-du.sa.band78.51prb.usrpb210.ho-pci0.conf
│   │   │   ├── gnb-du.sa.band78.51prb.usrpb210.ho-pci1.conf
│   │   │   ├── gnb.nsa.band78.106prb.usrpb200.conf
│   │   │   ├── gnb-pnf.band66.rfsim.conf
│   │   │   ├── gnb-pnf.band77.usrpn310.4x4.conf
│   │   │   ├── gnb-pnf.sa.band77.273prb.fhi72.4x4-4L-vvdn.conf
│   │   │   ├── gnb.sa.band254.u0.25prb.rfsim.ntn.conf
│   │   │   ├── gnb.sa.band254.u0.25prb.rfsim.ntn-leo.conf
│   │   │   ├── gnb.sa.band257.u3.66prb.rfsim.conf
│   │   │   ├── gnb.sa.band66.106prb.rfsim.conf
│   │   │   ├── gnb.sa.band77.162prb.usrpn310.2x2.conf
│   │   │   ├── gnb.sa.band77.273prb.fhi72.4x4-4layers-vvdn.conf
│   │   │   ├── gnb.sa.band77.273prb.fhi72.4x4-vvdn.conf
│   │   │   ├── gnb.sa.band77.273prb.usrpn310.2x2.conf
│   │   │   ├── gnb.sa.band77.51prb.usrpb200.n2-ho.conf
│   │   │   ├── gnb.sa.band78.106prb.fhi72.4x4-benetel550-9b-mplane.conf
│   │   │   ├── gnb.sa.band78.106prb.n310.7ds2u.conf
│   │   │   ├── gnb.sa.band78.106prb.rfsim.conf
│   │   │   ├── gnb.sa.band78.106prb.rfsim.flexric.conf
│   │   │   ├── gnb.sa.band78.106prb.rfsim.neighbour.conf
│   │   │   ├── gnb.sa.band78.106prb.rfsim.prs.conf
│   │   │   ├── gnb.sa.band78.106prb.rfsim.yaml
│   │   │   ├── gnb.sa.band78.106prb.usrpb200.sc-fdma-deltaMCS.conf
│   │   │   ├── gnb.sa.band78.106prb.vrtsim.2x2.yaml
│   │   │   ├── gnb.sa.band78.24prb.rfsim.conf
│   │   │   ├── gnb.sa.band78.273prb.fhi72.2x2-benetel550-9b-mplane.conf
│   │   │   ├── gnb.sa.band78.273prb.rfsim.2x2.conf
│   │   │   ├── gnb.sa.band78.51prb.aw2s.ddsuu.2x2.conf
│   │   │   ├── gnb.sa.band78.51prb.aw2s.ddsuu.conf
│   │   │   ├── gnb.sa.band78.51prb.usrpb200.conf
│   │   │   ├── gnb-vnf.sa.band66.u0.25prb.nfapi.conf
│   │   │   ├── gnb-vnf.sa.band77.162prb.nfapi.4x4.conf
│   │   │   ├── gnb-vnf.sa.band77.273prb.fhi72.4x4-4L-vvdn.conf
│   │   │   ├── gnb-vnf.sa.band78.273prb.aerial.conf
│   │   │   ├── gnb-vnf.sa.band78.273prb.aerial.ul-heavy.conf
│   │   │   ├── gnb-vnf.sa.band78.78prb.aerial.conf
│   │   │   ├── lteue.band7.25prb.l2sim.conf
│   │   │   ├── lteue.rfsim.conf
│   │   │   ├── lteue.usim-ci.conf
│   │   │   ├── lteue.usim-ci-magma.conf
│   │   │   ├── lte-ue.usim.conf
│   │   │   ├── lteue.usim-mbs.conf
│   │   │   ├── neighbour-config.conf
│   │   │   ├── neighbour-config-ho.conf
│   │   │   ├── nrue.band78.106prb.l2sim.conf
│   │   │   ├── nrue.band78.106prb.prs.conf
│   │   │   ├── nrue.uicc.2pdu.conf
│   │   │   ├── nrue.uicc.conf
│   │   │   ├── nrue.uicc.ntn-leo.conf
│   │   │   ├── nrue.uicc.yaml
│   │   │   ├── nrue.vrtsim.chanmod.yaml
│   │   │   ├── README.md
│   │   │   ├── ue.sa.conf
│   │   │   └── untested
│   │   ├── constants.py
│   │   ├── datalog_rt_stats.100.2x2.fhi72.cacofonix.yaml
│   │   ├── datalog_rt_stats.100.2x2.yaml
│   │   ├── datalog_rt_stats.100.4x4.fhi72.yaml
│   │   ├── datalog_rt_stats.1x1.60.yaml
│   │   ├── datalog_rt_stats.2x2.yaml
│   │   ├── datalog_rt_stats.60.2x2.yaml
│   │   ├── datalog_rt_stats.default.yaml
│   │   ├── docker
│   │   │   ├── Dockerfile.build.optional.ubuntu
│   │   │   ├── Dockerfile.channelsim.ubuntu
│   │   │   ├── Dockerfile.formatting.ubuntu
│   │   │   ├── Dockerfile.physim.cuda.ubuntu
│   │   │   ├── Dockerfile.physim.ubuntu
│   │   │   ├── Dockerfile.unittest.cuda.ubuntu
│   │   │   └── Dockerfile.unittest.ubuntu
│   │   ├── fail.sh
│   │   ├── helpreadme.py
│   │   ├── Jenkinsfile
│   │   ├── Jenkinsfile-colosseum
│   │   ├── Jenkinsfile-GitLab-Container
│   │   ├── Jenkinsfile-push-local-repo
│   │   ├── Jenkinsfile-push-registry
│   │   ├── Jenkinsfile-scheduled-run
│   │   ├── main.py
│   │   ├── mbim_scripts
│   │   │   ├── mbim-set-ip.sh
│   │   │   ├── start_quectel_mbim.sh
│   │   │   └── stop_quectel_mbim.sh
│   │   ├── pre-ci-check.sh
│   │   ├── provideUniqueImageTag.py
│   │   ├── ran.py
│   │   ├── README.md
│   │   ├── run_locally.sh
│   │   ├── scripts
│   │   │   ├── create_workspace.sh
│   │   │   ├── docker-build-and-deploy-chansim.sh
│   │   │   ├── docker-build-and-deploy-physims-cuda.sh
│   │   │   ├── docker-build-and-deploy-physims.sh
│   │   │   ├── magma-epc-deploy.sh
│   │   │   ├── magma-epc-logcollect.sh
│   │   │   ├── oc-chart-deploy.sh
│   │   │   ├── oc-chart-undeploy.sh
│   │   │   ├── oc-cn5g-deploy.sh
│   │   │   ├── oc-cn5g-logcollect.sh
│   │   │   ├── oc-cn5g-undeploy.sh
│   │   │   ├── oc-deploy-physims.sh
│   │   │   ├── set-and-verify-distance-prs.sh
│   │   │   ├── set-wnc-bandwidth.sh
│   │   │   ├── source-deploy-physims.sh
│   │   │   ├── sys-info.sh
│   │   │   ├── vvdn-activate-carriers.sh
│   │   │   └── vvdn-inactivate-carriers.sh
│   │   ├── tests
│   │   │   ├── analysis
│   │   │   ├── analysis.py
│   │   │   ├── build.py
│   │   │   ├── cmd.py
│   │   │   ├── config
│   │   │   ├── corenetwork.py
│   │   │   ├── deployment.py
│   │   │   ├── iperf-analysis.py
│   │   │   ├── log
│   │   │   ├── log-analysis
│   │   │   ├── log-analysis.py
│   │   │   ├── module.py
│   │   │   ├── ping-iperf.py
│   │   │   ├── pull-clean-int-registry.py
│   │   │   ├── README.md
│   │   │   ├── script-deployment.py
│   │   │   ├── scripts
│   │   │   ├── simple-dep
│   │   │   ├── simple-fail
│   │   │   ├── simple-fail-2svc
│   │   │   ├── simple-undep
│   │   │   └── test-runner
│   │   ├── xml_class_list.yml
│   │   ├── xml_files
│   │   │   ├── cluster_image_build.xml
│   │   │   ├── container_4g_l2sim_tdd.xml
│   │   │   ├── container_4g_rfsim_fdd_05MHz_noS1.xml
│   │   │   ├── container_4g_rfsim_fdd_05MHz.xml
│   │   │   ├── container_4g_rfsim_fdd_10MHz.xml
│   │   │   ├── container_4g_rfsim_fdd_20MHz.xml
│   │   │   ├── container_4g_rfsim_fembms.xml
│   │   │   ├── container_4g_rfsim_mbms.xml
│   │   │   ├── container_4g_rfsim_tdd_05MHz.xml
│   │   │   ├── container_5g_e1_rfsim.xml
│   │   │   ├── container_5g_f1_rfsim.xml
│   │   │   ├── container_5g_fdd_rfsim.xml
│   │   │   ├── container_5g_flexric_rfsim.xml
│   │   │   ├── container_5g_rfsim_24prb.xml
│   │   │   ├── container_5g_rfsim_2x2.xml
│   │   │   ├── container_5g_rfsim_fdd_phytest.xml
│   │   │   ├── container_5g_rfsim_fr2_66prb.xml
│   │   │   ├── container_5g_rfsim_multiue.xml
│   │   │   ├── container_5g_rfsim_n2_ho.xml
│   │   │   ├── container_5g_rfsim_ntn_geo.xml
│   │   │   ├── container_5g_rfsim_ntn_leo.xml
│   │   │   ├── container_5g_rfsim_prs.xml
│   │   │   ├── container_5g_rfsim_sidelink.xml
│   │   │   ├── container_5g_rfsim_simple.xml
│   │   │   ├── container_5g_rfsim_tdd_dora.xml
│   │   │   ├── container_5g_rfsim_u0_25prb.xml
│   │   │   ├── container_5g_rfsim.xml
│   │   │   ├── container_5g_vrtsim_chanmod_gh.xml
│   │   │   ├── container_5g_vrtsim_chanmod.xml
│   │   │   ├── container_5g_vrtsim_cirdb.xml
│   │   │   ├── container_5g_vrtsim_multiue_gh.xml
│   │   │   ├── container_5g_zmq_2x2.xml
│   │   │   ├── container_5g_zmq_ocudu_1x1.xml
│   │   │   ├── container_5g_zmq_ocudu_2x2.xml
│   │   │   ├── container_build_run_gh_tests.xml
│   │   │   ├── container_build_run_tests.xml
│   │   │   ├── container_image_build_arm.xml
│   │   │   ├── container_image_build_cross.xml
│   │   │   ├── container_image_build_jetson.xml
│   │   │   ├── container_image_build_t2.xml
│   │   │   ├── container_image_build.xml
│   │   │   ├── container_lte_b200_fdd_05Mhz_tm1_if4_5.xml
│   │   │   ├── container_lte_b200_fdd_05Mhz_tm1_no_rrc_activity.xml
│   │   │   ├── container_lte_b200_fdd_05Mhz_tm1.xml
│   │   │   ├── container_lte_b200_fdd_10Mhz_tm1_cdrx.xml
│   │   │   ├── container_lte_b200_fdd_10Mhz_tm1_oaiue.xml
│   │   │   ├── container_lte_b200_fdd_10Mhz_tm1.xml
│   │   │   ├── container_lte_b200_fdd_20Mhz_tm1.xml
│   │   │   ├── container_lte_b200_tdd_05Mhz_tm1_if4_5.xml
│   │   │   ├── container_lte_b200_tdd_05Mhz_tm1.xml
│   │   │   ├── container_lte_b200_tdd_10Mhz_tm1.xml
│   │   │   ├── container_lte_b200_tdd_20Mhz_tm1_default_scheduler.xml
│   │   │   ├── container_lte_b200_tdd_20Mhz_tm1.xml
│   │   │   ├── container_lte_n3xx_tdd_2x2_tm1.xml
│   │   │   ├── container_lte_n3xx_tdd_2x2_tm2.xml
│   │   │   ├── container_nsa_b200_quectel.xml
│   │   │   ├── container_sa_aerial_cn_start.xml
│   │   │   ├── container_sa_aerial_cn_stop.xml
│   │   │   ├── container_sa_aerial_quectel_ul_heavy.xml
│   │   │   ├── container_sa_aerial_quectel.xml
│   │   │   ├── container_sa_aw2s_asue_2x2.xml
│   │   │   ├── container_sa_aw2s_asue.xml
│   │   │   ├── container_sa_b200_nrue_jetson.xml
│   │   │   ├── container_sa_b200_quectel.xml
│   │   │   ├── container_sa_e1_b200_quectel.xml
│   │   │   ├── container_sa_f1_b200_quectel.xml
│   │   │   ├── container_sa_f1_ho_b210_quectel.xml
│   │   │   ├── container_sa_fhi72_benetel_2x2_100MHz_9b_mplane_amariue.xml
│   │   │   ├── container_sa_fhi72_benetel_4x4_40MHz_9b_mplane_amariue.xml
│   │   │   ├── container_sa_fhi72_benetel_4x4_up2.xml
│   │   │   ├── container_sa_fhi72_benetel_8x8_up3.xml
│   │   │   ├── container_sa_fhi72_liteon_4x4_up2.xml
│   │   │   ├── container_sa_fhi72_metanoia_4x4_up2.xml
│   │   │   ├── container_sa_fhi72_vvdn_4x4_monolithic_up2.xml
│   │   │   ├── container_sa_fhi72_vvdn_4x4_up2_nfapi.xml
│   │   │   ├── container_sa_fhi72_vvdn_4x4_up2.xml
│   │   │   ├── container_sa_fhi72_vvdn_up2.xml
│   │   │   ├── container_sa_n2_ho_b210_quectel.xml
│   │   │   ├── container_sa_n310_2X2_100MHz_quectel.xml
│   │   │   ├── container_sa_n310_2X2_60MHz_quectel.xml
│   │   │   ├── container_sa_n310_4X4_60MHz_quectel.xml
│   │   │   ├── container_sa_n310_nrue_longrun.xml
│   │   │   ├── container_sa_n310_nrue.xml
│   │   │   ├── container_sa_sc_b200_quectel.xml
│   │   │   ├── formatting_check.xml
│   │   │   ├── fr1_5gc_closure.xml
│   │   │   ├── fr1_5gc_start.xml
│   │   │   ├── fr1_cn5g_basic_deploy.xml
│   │   │   ├── fr1_cn5g_basic_undeploy.xml
│   │   │   ├── fr1_epc_closure.xml
│   │   │   ├── fr1_epc_start_verizon.xml
│   │   │   ├── fr1_epc_start.xml
│   │   │   ├── fr1_oai_cn_deploy.xml
│   │   │   ├── fr1_oai_cn_undeploy.xml
│   │   │   ├── gnb_phytest_fhi7.2_docker_cacofonix.xml
│   │   │   ├── gnb_phytest_fhi7.2_docker.xml
│   │   │   ├── gnb_phytest_rfemulator_run_100_2x2.xml
│   │   │   ├── gnb_phytest_usrp_run_100_2x2.xml
│   │   │   ├── gnb_phytest_usrp_run_60_2x2.xml
│   │   │   ├── gnb_phytest_usrp_run_60.xml
│   │   │   ├── gnb_phytest_usrp_run.xml
│   │   │   ├── gnb_usrp_build.xml
│   │   │   ├── lte_oai_cn_deploy.xml
│   │   │   ├── lte_oai_cn_undeploy.xml
│   │   │   ├── physim_4g_deploy_run.xml
│   │   │   ├── physim_5g_deploy_run.xml
│   │   │   ├── physim_gracehopper.xml
│   │   │   ├── physim_timed_gracehopper.xml
│   │   │   ├── sa_cn5g_20897_closure.xml
│   │   │   ├── sa_cn5g_20897_start.xml
│   │   │   ├── sa_cn5g_closure.xml
│   │   │   ├── sa_cn5g_start.xml
│   │   │   ├── t2_offload_physim_enc_dec.xml
│   │   │   ├── test_channel_sim_gracehopper.xml
│   │   │   └── test_physim_cuda_gracehopper.xml
│   │   └── yaml_files
│   │       ├── 4g_l2sim_fdd
│   │       ├── 4g_rfsimulator_fdd_05MHz
│   │       ├── 4g_rfsimulator_fdd_05MHz_noS1
│   │       ├── 4g_rfsimulator_fdd_10MHz
│   │       ├── 4g_rfsimulator_fdd_20MHz
│   │       ├── 4g_rfsimulator_fembms
│   │       ├── 4g_rfsimulator_mbms
│   │       ├── 4g_rfsimulator_tdd_05MHz
│   │       ├── 5g_f1_rfsimulator
│   │       ├── 5g_fdd_rfsimulator
│   │       ├── 5g_rfsimulator
│   │       ├── 5g_rfsimulator_24prb
│   │       ├── 5g_rfsimulator_2x2
│   │       ├── 5g_rfsimulator_e1
│   │       ├── 5g_rfsimulator_fdd_phytest
│   │       ├── 5g_rfsimulator_flexric
│   │       ├── 5g_rfsimulator_fr2_66prb
│   │       ├── 5g_rfsimulator_multiue
│   │       ├── 5g_rfsimulator_n2_ho
│   │       ├── 5g_rfsimulator_ntn_geo
│   │       ├── 5g_rfsimulator_ntn_leo
│   │       ├── 5g_rfsimulator_prs
│   │       ├── 5g_rfsimulator_sidelink
│   │       ├── 5g_rfsimulator_tdd_dora
│   │       ├── 5g_rfsimulator_u0_25prb
│   │       ├── 5g_sa_f1_b210_ho
│   │       ├── 5g_sa_n2_ho_b210
│   │       ├── 5g_sa_n310_2x2_100MHz
│   │       ├── 5g_sa_n310_2x2_60MHz
│   │       ├── 5g_sa_n310_4x4_60MHz
│   │       ├── 5g_sa_n310_gnb
│   │       ├── 5g_sa_n310_nrue
│   │       ├── 5g_vrtsim_chanmod
│   │       ├── 5g_vrtsim_cirdb
│   │       ├── 5g_vrtsim_multiue
│   │       ├── 5g_zmq_radio_1x1_ocudu
│   │       ├── 5g_zmq_radio_2x2
│   │       ├── 5g_zmq_radio_2x2_ocudu
│   │       ├── fr1_epc_20897
│   │       ├── local_common_overrides
│   │       ├── lte_b200_fdd_05Mhz_if4.5
│   │       ├── lte_b200_fdd_05Mhz_tm1
│   │       ├── lte_b200_fdd_05Mhz_tm1_no_rrc_activity
│   │       ├── lte_b200_fdd_10Mhz_oai_ue_magma
│   │       ├── lte_b200_fdd_10Mhz_tm1
│   │       ├── lte_b200_fdd_10Mhz_tm1_cdrx
│   │       ├── lte_b200_fdd_10Mhz_tm1_magma
│   │       ├── lte_b200_fdd_20Mhz_tm1
│   │       ├── lte_b200_tdd_05Mhz_if4.5
│   │       ├── lte_b200_tdd_05Mhz_tm1
│   │       ├── lte_b200_tdd_05Mhz_tm2
│   │       ├── lte_b200_tdd_10Mhz_tm1
│   │       ├── lte_b200_tdd_20Mhz_tm1
│   │       ├── lte_b200_tdd_20Mhz_tm1_default_scheduler
│   │       ├── lte_n3xx_tdd_2x2_tm1
│   │       ├── lte_n3xx_tdd_2x2_tm2
│   │       ├── magma_lte_20892
│   │       ├── magma_nsa_20897
│   │       ├── nsa_b200_enb
│   │       ├── nsa_b200_gnb
│   │       ├── phytest_fhi72
│   │       ├── phytest_fhi72_cacofonix
│   │       ├── sa_aw2s_2x2_gnb
│   │       ├── sa_aw2s_gnb
│   │       ├── sa_b200_gnb
│   │       ├── sa_b200_jetson_nrue
│   │       ├── sa_e1_b200_gnb
│   │       ├── sa_f1_b200_gnb
│   │       ├── sa_fhi_7.2_benetel_4x4_du
│   │       ├── sa_fhi_7.2_benetel550_2x2_100MHz_9b_mplane_gnb
│   │       ├── sa_fhi_7.2_benetel550_4x4_40MHz_9b_mplane_gnb
│   │       ├── sa_fhi_7.2_benetel_8x8_du
│   │       ├── sa_fhi_7.2_liteon_4x4_gnb
│   │       ├── sa_fhi_7.2_metanoia_4x4_gnb
│   │       ├── sa_fhi_7.2_vvdn_4x4_du
│   │       ├── sa_fhi_7.2_vvdn_4x4_monolithic_gnb
│   │       ├── sa_fhi_7.2_vvdn_4x4_nfapi
│   │       ├── sa_fhi_7.2_vvdn_gnb
│   │       ├── sa_gnb_aerial
│   │       ├── sa_gnb_aerial_30MHz
│   │       ├── sa_gnb_aerial_ul
│   │       └── sa_sc_b200_gnb
│   ├── CMakeLists.txt
│   ├── CMakePresets.json
│   ├── cmake_targets
│   │   ├── at_commands
│   │   │   └── CMakeLists.txt
│   │   ├── build_oai
│   │   ├── CPM.cmake
│   │   ├── cross-arm.cmake
│   │   ├── macros.cmake
│   │   ├── ran_build
│   │   │   └── build
│   │   └── tools
│   │       ├── build_helper
│   │       ├── install_libraries_to_system.patch
│   │       ├── install_wls_lib.patch
│   │       ├── MODULES
│   │       ├── oran_fhi_integration_patches
│   │       ├── test_helper
│   │       ├── uhd-3.15-tdd-patch.diff
│   │       ├── uhd-4.5plus-tdd-patch.diff
│   │       └── uhd-4.x-tdd-patch.diff
│   ├── common
│   │   ├── 5g_platform_types.h
│   │   ├── cmake_defs.h.in
│   │   ├── CMakeLists.txt
│   │   ├── config
│   │   │   ├── config_cmdline.c
│   │   │   ├── config_common.c
│   │   │   ├── config_common.h
│   │   │   ├── config_load_configmodule.c
│   │   │   ├── config_load_configmodule.h
│   │   │   ├── config_paramdesc.h
│   │   │   ├── config_userapi.c
│   │   │   ├── config_userapi.h
│   │   │   ├── DOC
│   │   │   ├── libconfig
│   │   │   ├── tests
│   │   │   └── yaml
│   │   ├── instrumentation.h
│   │   ├── ngran_types.h
│   │   ├── oai_version.h.in
│   │   ├── openairinterface5g_limits.h
│   │   ├── platform_constants.h
│   │   ├── platform_types.h
│   │   ├── ran_context.h
│   │   └── utils
│   │       ├── actor
│   │       ├── alg
│   │       ├── assertions.h
│   │       ├── barrier
│   │       ├── bits.c
│   │       ├── bits.h
│   │       ├── CMakeLists.txt
│   │       ├── collection
│   │       ├── config.h
│   │       ├── data_recording
│   │       ├── DOC
│   │       ├── ds
│   │       ├── eq_check.h
│   │       ├── fsn.c
│   │       ├── fsn.h
│   │       ├── load_module_shlib.c
│   │       ├── load_module_shlib.h
│   │       ├── LOG
│   │       ├── lte
│   │       ├── mem
│   │       ├── minimal_stub.c
│   │       ├── nr
│   │       ├── oai_asn1.h
│   │       ├── ocp_itti
│   │       ├── shm_iq_channel
│   │       ├── simple_executable.h
│   │       ├── system.c
│   │       ├── system.h
│   │       ├── T
│   │       ├── telnetsrv
│   │       ├── tests
│   │       ├── threadPool
│   │       ├── time_manager
│   │       ├── time_meas.c
│   │       ├── time_meas.h
│   │       ├── time_stat.c
│   │       ├── time_stat.h
│   │       ├── tuntap_if.c
│   │       ├── tuntap_if.h
│   │       ├── utils.c
│   │       ├── utils.h
│   │       ├── var_array.h
│   │       └── websrv
│   ├── CONTRIBUTING.md
│   ├── doc
│   │   ├── 5Gnas.md
│   │   ├── Aerial_FAPI_Split_Tutorial.md
│   │   ├── analog_beamforming.md
│   │   ├── BUILD.md
│   │   ├── clang-format.md
│   │   ├── CMakeLists.txt
│   │   ├── code-style-contrib.md
│   │   ├── cross-compile.md
│   │   ├── d2d_emulator_setup.md
│   │   ├── data_recording.md
│   │   ├── dev_tools
│   │   │   ├── sanitizers.md
│   │   │   └── tracy.md
│   │   ├── doc_best_practices.md
│   │   ├── Doxyfile
│   │   ├── E1AP
│   │   │   ├── e1ap_procedures.md
│   │   │   ├── E1-design.md
│   │   │   └── images
│   │   ├── environment-variables.md
│   │   ├── episys
│   │   │   ├── Channel_Abstraction_UE_Handling_LTE.PNG
│   │   │   ├── functional_diagram_proxy_lte.png
│   │   │   ├── functional_diagram_proxy_nsa.png
│   │   │   ├── lte_mode_l2_emulator
│   │   │   ├── nsa_mode_l2_emulator
│   │   │   └── Proxy_Interface_Diagram.PNG
│   │   ├── F1AP
│   │   │   ├── F1AP-lib.md
│   │   │   └── F1-design.md
│   │   ├── FEATURE_SET.md
│   │   ├── GET_SOURCES.md
│   │   ├── gNB_frequency_setup.md
│   │   ├── handover-tutorial.md
│   │   ├── images
│   │   │   ├── attach_signaling_scheme.jpg
│   │   │   ├── data_recording_arch.svg
│   │   │   ├── data_serialization_tx_scrambled_bit_message.svg
│   │   │   ├── docker-deploy-oai-7-2.drawio.xml
│   │   │   ├── docker-deploy-oai-7-2.png
│   │   │   ├── L2-sim-noS1-2-host-deployment.png
│   │   │   ├── L2-sim-S1-3-host-deployment.png
│   │   │   ├── L2-sim-single-server-deployment.png
│   │   │   ├── mimo_antenna_ports.png
│   │   │   ├── nr-ue-threads.svg
│   │   │   ├── oai_enb_block_diagram.png
│   │   │   ├── oai_enb_func_split_arch.png
│   │   │   ├── oai_final_logo.png
│   │   │   ├── oai_fr1_lab.jpg
│   │   │   ├── oai_fr1_setup.jpg
│   │   │   ├── oai_logo.png
│   │   │   ├── oai_lte_enb_func_split_arch.png
│   │   │   ├── PRS_CFR_FR2_64PRB_8rsc.PNG
│   │   │   ├── PRS_CIR_FR2_64PRB_8rsc.PNG
│   │   │   ├── sigmf_dataset.svg
│   │   │   └── USRP_tune_offset.png
│   │   ├── iqrecordplayer_usage.md
│   │   ├── L1SIM.md
│   │   ├── L2NFAPI.md
│   │   ├── L2NFAPI_NOS1.md
│   │   ├── L2NFAPI_S1.md
│   │   ├── LDPC_OFFLOAD_SETUP.md
│   │   ├── MAC
│   │   │   ├── mac-usage.md
│   │   │   ├── scheduler-architecture.md
│   │   │   └── TDD_Frame_Structure.png
│   │   ├── nfapi.md
│   │   ├── NR_NFAPI_archi.md
│   │   ├── NR_SA_Tutorial_COTS_UE.md
│   │   ├── NR_SA_Tutorial_OAI_CN5G.md
│   │   ├── NR_SA_Tutorial_OAI_multi_UE.md
│   │   ├── NR_SA_Tutorial_OAI_nrUE.md
│   │   ├── nr-ue-design.md
│   │   ├── ntn-configuration.md
│   │   ├── openair_header.tex
│   │   ├── ORAN_FHI7.2_Tutorial.md
│   │   ├── packages.md
│   │   ├── physical-simulators.md
│   │   ├── rach_processing_in_gNB.md
│   │   ├── README.md
│   │   ├── RRC
│   │   │   ├── ho.mmd
│   │   │   ├── ho.png
│   │   │   ├── rrc-dev.md
│   │   │   └── rrc-usage.md
│   │   ├── RUNMODEM.md
│   │   ├── runmodem-nrue.md
│   │   ├── RUN_NR_PRS.md
│   │   ├── Supported_Hardware_Operating_System.md
│   │   ├── SW-archi-graph.md
│   │   ├── SW_archi.md
│   │   ├── system_requirements.md
│   │   ├── testbenches_doc_resources
│   │   │   ├── 4g-faraday-bench.pdf
│   │   │   ├── 4g-faraday-bench.png
│   │   │   ├── 4g-faraday-bench.tex
│   │   │   ├── 5g-aw2s-bench.pdf
│   │   │   ├── 5g-aw2s-bench.png
│   │   │   ├── 5g-aw2s-bench.tex
│   │   │   ├── 5g-nrue-bench.pdf
│   │   │   ├── 5g-nrue-bench.png
│   │   │   ├── 5g-nrue-bench.tex
│   │   │   ├── 5g-nsa-faraday-bench.pdf
│   │   │   ├── 5g-nsa-faraday-bench.png
│   │   │   ├── 5g-nsa-faraday-bench.tex
│   │   │   ├── 5g-ota-bench.pdf
│   │   │   ├── 5g-ota-bench.png
│   │   │   ├── 5g-ota-bench.tex
│   │   │   ├── amariue.png
│   │   │   ├── antenna.pdf
│   │   │   ├── aw2s.png
│   │   │   ├── b200-mini.png
│   │   │   ├── b210.jpg
│   │   │   ├── benches.vsdx
│   │   │   ├── n310.png
│   │   │   ├── openshift.png
│   │   │   ├── phone.pdf
│   │   │   ├── quectel.png
│   │   │   ├── server.pdf
│   │   │   └── x310.jpg
│   │   ├── TESTBenches.md
│   │   ├── TESTING_OAI_NSA_COTS_UE.md
│   │   ├── testing_oai_nsa_w_cots_ue_resources
│   │   │   ├── enb.conf
│   │   │   ├── gnb.conf
│   │   │   ├── oai_enb.log
│   │   │   ├── oai_fr1_setup.vsdx
│   │   │   └── oai_gnb.log
│   │   ├── time_management.md
│   │   ├── tuning_and_security.md
│   │   ├── tutorial_resources
│   │   │   ├── oai-cn5g
│   │   │   └── positioning
│   │   ├── UL_MIMO.md
│   │   └── UnitTests.md
│   ├── docker
│   │   ├── debug_core_image.sh
│   │   ├── Dockerfile.base.rhel9
│   │   ├── Dockerfile.base.rocky
│   │   ├── Dockerfile.base.ubuntu
│   │   ├── Dockerfile.base.ubuntu.cross-arm64
│   │   ├── Dockerfile.build.fhi72.native_arm.ubuntu
│   │   ├── Dockerfile.build.fhi72.rhel9
│   │   ├── Dockerfile.build.fhi72.t2.ubuntu
│   │   ├── Dockerfile.build.fhi72.ubuntu
│   │   ├── Dockerfile.build.rhel9
│   │   ├── Dockerfile.build.rocky
│   │   ├── Dockerfile.build.ubuntu
│   │   ├── Dockerfile.build.ubuntu.cross-arm64
│   │   ├── Dockerfile.clang.rhel9
│   │   ├── Dockerfile.eNB.rhel9
│   │   ├── Dockerfile.eNB.rocky
│   │   ├── Dockerfile.eNB.ubuntu
│   │   ├── Dockerfile.gNB.aerial.ubuntu
│   │   ├── Dockerfile.gNB.aerial.ubuntu.sanitize-address
│   │   ├── Dockerfile.gNB.aw2s.rhel9
│   │   ├── Dockerfile.gNB.aw2s.rocky
│   │   ├── Dockerfile.gNB.aw2s.ubuntu
│   │   ├── Dockerfile.gNB.fhi72.rhel9
│   │   ├── Dockerfile.gNB.fhi72.rocky
│   │   ├── Dockerfile.gNB.fhi72.t2.ubuntu
│   │   ├── Dockerfile.gNB.fhi72.ubuntu
│   │   ├── Dockerfile.gNB.rhel9
│   │   ├── Dockerfile.gNB.rocky
│   │   ├── Dockerfile.gNB.ubuntu
│   │   ├── Dockerfile.lteRU.rhel9
│   │   ├── Dockerfile.lteRU.ubuntu
│   │   ├── Dockerfile.lteUE.rhel9
│   │   ├── Dockerfile.lteUE.rocky
│   │   ├── Dockerfile.lteUE.ubuntu
│   │   ├── Dockerfile.nr-cuup.rhel9
│   │   ├── Dockerfile.nr-cuup.rocky
│   │   ├── Dockerfile.nr-cuup.ubuntu
│   │   ├── Dockerfile.nrORU.fhi72.ubuntu
│   │   ├── Dockerfile.nrUE.rhel9
│   │   ├── Dockerfile.nrUE.rocky
│   │   ├── Dockerfile.nrUE.ubuntu
│   │   ├── Dockerfile.phySim.rhel9
│   │   ├── README.md
│   │   └── scripts
│   │       ├── check-prach-io.sh
│   │       ├── enb_entrypoint.sh
│   │       ├── gnb-aw2s_entrypoint.sh
│   │       ├── gnb_entrypoint.sh
│   │       ├── lte_ru_entrypoint.sh
│   │       ├── lte_ue_entrypoint.sh
│   │       ├── nr_oru_entrypoint.sh
│   │       └── nr_ue_entrypoint.sh
│   ├── executables
│   │   ├── CMakeLists.txt
│   │   ├── create_tasks.c
│   │   ├── create_tasks.h
│   │   ├── create_tasks_mbms.c
│   │   ├── create_tasks_ue.c
│   │   ├── lte-enb.c
│   │   ├── lte-ru.c
│   │   ├── lte-softmodem.c
│   │   ├── lte-softmodem.h
│   │   ├── lte-ue.c
│   │   ├── lte-uesoftmodem.c
│   │   ├── main_nr_ru.c
│   │   ├── main_ru.c
│   │   ├── nr-cuup.c
│   │   ├── nr-gnb.c
│   │   ├── nr-ru.c
│   │   ├── nr-softmodem.c
│   │   ├── nr-softmodem-common.h
│   │   ├── nr-softmodem.h
│   │   ├── nr-ue.c
│   │   ├── nr-ue-ru.c
│   │   ├── nr-ue-ru.h
│   │   ├── nr-uesoftmodem.c
│   │   ├── nr-uesoftmodem.h
│   │   ├── position_interface.c
│   │   ├── position_interface.h
│   │   ├── ru_control.c
│   │   ├── softmodem-common.c
│   │   ├── softmodem-common.h
│   │   ├── stats.c
│   │   ├── stats.h
│   │   ├── thread-common.h
│   │   └── uecap.raw
│   ├── fronthaul
│   │   ├── CMakeLists.txt
│   │   ├── core
│   │   │   ├── CMakeLists.txt
│   │   │   ├── fh_recv.c
│   │   │   ├── fh_recv.h
│   │   │   ├── fh_send.c
│   │   │   ├── fh_send.h
│   │   │   ├── fh_timer.c
│   │   │   ├── fh_timer.h
│   │   │   ├── README.md
│   │   │   └── tests
│   │   ├── oru
│   │   │   ├── CMakeLists.txt
│   │   │   ├── oru_fh.c
│   │   │   ├── oru_fh.h
│   │   │   ├── oru_io.c
│   │   │   ├── oru_io.h
│   │   │   ├── oru_packet_processor.c
│   │   │   ├── oru_packet_processor.h
│   │   │   └── tests
│   │   ├── README.md
│   │   └── xran_pkt
│   │       ├── CMakeLists.txt
│   │       ├── tests
│   │       ├── xran_pkt_api.c
│   │       ├── xran_pkt_api.h
│   │       ├── xran_pkt_cp.h
│   │       ├── xran_pkt.h
│   │       └── xran_pkt_up.h
│   ├── gnb.log
│   ├── grep-tracer.log
│   ├── LICENSE
│   ├── LICENSES
│   │   ├── deprecated
│   │   │   └── OAI-PL-v1.1.txt
│   │   ├── exception
│   │   │   ├── Apache-2.0.txt
│   │   │   ├── BSD-2-Clause.txt
│   │   │   └── BSD-3-Clause.txt
│   │   └── preferred
│   │       ├── CC-BY-4.0.txt
│   │       ├── CSSL-v1.0.txt
│   │       └── MIT.txt
│   ├── logs-build-oai.log
│   ├── maketags
│   ├── nfapi
│   │   ├── CHANGES.md
│   │   ├── CMakeLists.txt
│   │   ├── oai_integration
│   │   │   ├── aerial
│   │   │   ├── CMakeLists.txt
│   │   │   ├── gnb_ind_vars.c
│   │   │   ├── gnb_ind_vars.h
│   │   │   ├── nfapi.c
│   │   │   ├── nfapi_pnf.c
│   │   │   ├── nfapi_pnf.h
│   │   │   ├── nfapi_vnf.c
│   │   │   ├── nfapi_vnf.h
│   │   │   ├── socket
│   │   │   ├── vendor_ext.h
│   │   │   └── wls_integration
│   │   ├── open-nFAPI
│   │   │   ├── CHANGELOG.md
│   │   │   ├── CMakeLists.txt
│   │   │   ├── common
│   │   │   ├── configure.ac
│   │   │   ├── docs
│   │   │   ├── fapi
│   │   │   ├── integration_tests
│   │   │   ├── LICENSE.md
│   │   │   ├── Makefile.am
│   │   │   ├── nfapi
│   │   │   ├── pnf
│   │   │   ├── pnf_sim
│   │   │   ├── README.md
│   │   │   ├── sim_common
│   │   │   ├── utils
│   │   │   ├── vnf
│   │   │   ├── vnf_sim
│   │   │   └── xml
│   │   ├── README
│   │   └── tests
│   │       ├── CMakeLists.txt
│   │       ├── nr_fapi_test.h
│   │       ├── p5
│   │       └── p7
│   ├── NOTICE
│   ├── nrL1_stats.log
│   ├── nrL1_UE_stats-0.log
│   ├── nrMAC_stats.log
│   ├── nrRRC_stats.log
│   ├── oaienv
│   ├── openair1
│   │   ├── CMakeLists.txt
│   │   ├── PHY
│   │   │   ├── CMakeLists.txt
│   │   │   ├── CODING
│   │   │   ├── defs_common.h
│   │   │   ├── defs_eNB.h
│   │   │   ├── defs_gNB.h
│   │   │   ├── defs_L1_NB_IoT.h
│   │   │   ├── defs_nr_common.h
│   │   │   ├── defs_nr_sl_UE.h
│   │   │   ├── defs_nr_UE.h
│   │   │   ├── defs_RU.h
│   │   │   ├── defs_UE.h
│   │   │   ├── gold.h
│   │   │   ├── if4_tools.c
│   │   │   ├── if4_tools.h
│   │   │   ├── impl_defs_lte_NB_IoT.h
│   │   │   ├── impl_defs_nr.h
│   │   │   ├── impl_defs_top.h
│   │   │   ├── impl_defs_top_NB_IoT.h
│   │   │   ├── INIT
│   │   │   ├── LTE_ESTIMATION
│   │   │   ├── LTE_REFSIG
│   │   │   ├── LTE_TRANSPORT
│   │   │   ├── LTE_UE_TRANSPORT
│   │   │   ├── MODULATION
│   │   │   ├── NR_ESTIMATION
│   │   │   ├── nr_phy_common
│   │   │   ├── NR_REFSIG
│   │   │   ├── NR_TRANSPORT
│   │   │   ├── NR_UE_ESTIMATION
│   │   │   ├── NR_UE_TRANSPORT
│   │   │   ├── phy_extern.h
│   │   │   ├── phy_extern_nr_ue.h
│   │   │   ├── phy_extern_ue.h
│   │   │   ├── phy_vars.h
│   │   │   ├── phy_vars_nr_ue.h
│   │   │   ├── phy_vars_ue.h
│   │   │   ├── sse_intrin.h
│   │   │   ├── TOOLS
│   │   │   ├── types.h
│   │   │   └── types_NB_IoT.h
│   │   ├── README.TXT
│   │   ├── SCHED
│   │   │   ├── fapi_l1.c
│   │   │   ├── fapi_l1.h
│   │   │   ├── nfapi_lte_dummy.c
│   │   │   ├── phy_mac_stub.c
│   │   │   ├── phy_procedures_lte_common.c
│   │   │   ├── phy_procedures_lte_eNb.c
│   │   │   ├── prach_procedures.c
│   │   │   ├── ru_procedures.c
│   │   │   ├── sched_common_extern.h
│   │   │   ├── sched_common.h
│   │   │   └── sched_eNB.h
│   │   ├── SCHED_NR
│   │   │   ├── nr_prach_procedures.c
│   │   │   ├── nr_ru_procedures.c
│   │   │   ├── phy_frame_config_nr.c
│   │   │   ├── phy_frame_config_nr.h
│   │   │   ├── phy_procedures_nr_gNB.c
│   │   │   └── sched_nr.h
│   │   ├── SCHED_NR_UE
│   │   │   ├── defs.h
│   │   │   ├── fapi_nr_ue_l1.c
│   │   │   ├── fapi_nr_ue_l1.h
│   │   │   ├── harq_nr.c
│   │   │   ├── harq_nr.h
│   │   │   ├── phy_procedures_nr_ue.c
│   │   │   ├── phy_procedures_nr_ue_sl.c
│   │   │   ├── phy_sch_processing_time.h
│   │   │   ├── pucch_uci_ue_nr.c
│   │   │   └── pucch_uci_ue_nr.h
│   │   ├── SCHED_UE
│   │   │   ├── phy_procedures_lte_ue.c
│   │   │   ├── pucch_pc.c
│   │   │   ├── pusch_pc.c
│   │   │   ├── sched_UE.h
│   │   │   └── srs_pc.c
│   │   └── SIMULATION
│   │       ├── CMakeLists.txt
│   │       ├── LTE_PHY
│   │       ├── NR_PHY
│   │       ├── RF
│   │       ├── tests
│   │       └── TOOLS
│   ├── openair2
│   │   ├── CMakeLists.txt
│   │   ├── COMMON
│   │   │   ├── as_message.h
│   │   │   ├── commonDef.h
│   │   │   ├── e1ap_messages_def.h
│   │   │   ├── e1ap_messages_types.h
│   │   │   ├── f1ap_messages_def.h
│   │   │   ├── f1ap_messages_types.h
│   │   │   ├── gtpv1_u_messages_def.h
│   │   │   ├── gtpv1_u_messages_types.h
│   │   │   ├── m2ap_messages_def.h
│   │   │   ├── m2ap_messages_types.h
│   │   │   ├── m3ap_messages_def.h
│   │   │   ├── m3ap_messages_types.h
│   │   │   ├── mac_messages_def.h
│   │   │   ├── mac_messages_types.h
│   │   │   ├── mac_rlc_primitives.h
│   │   │   ├── mac_rrc_primitives.h
│   │   │   ├── nas_messages_def.h
│   │   │   ├── nas_messages_types.h
│   │   │   ├── networkDef.h
│   │   │   ├── ngap_messages_def.h
│   │   │   ├── ngap_messages_types.h
│   │   │   ├── nrppa_messages_def.h
│   │   │   ├── nrppa_messages_types.h
│   │   │   ├── pdcp_messages_def.h
│   │   │   ├── pdcp_messages_types.h
│   │   │   ├── positioning_nr_paramdef.h
│   │   │   ├── prs_nr_paramdef.h
│   │   │   ├── rrc_messages_def.h
│   │   │   ├── rrc_messages_types.h
│   │   │   ├── rrm_constants.h
│   │   │   ├── s1ap_messages_def.h
│   │   │   ├── s1ap_messages_types.h
│   │   │   ├── sctp_messages_def.h
│   │   │   ├── sctp_messages_types.h
│   │   │   ├── x2ap_messages_def.h
│   │   │   ├── x2ap_messages_types.h
│   │   │   └── xnap_messages_types.h
│   │   ├── E1AP
│   │   │   ├── CMakeLists.txt
│   │   │   ├── e1ap_asnc.h
│   │   │   ├── e1ap.c
│   │   │   ├── e1ap_common.c
│   │   │   ├── e1ap_common.h
│   │   │   ├── e1ap_default_values.h
│   │   │   ├── e1ap.h
│   │   │   ├── e1ap_setup.c
│   │   │   ├── lib
│   │   │   ├── MESSAGES
│   │   │   └── tests
│   │   ├── E2AP
│   │   │   ├── CMakeLists.txt
│   │   │   ├── e2_agent_arg.c
│   │   │   ├── e2_agent_arg.h
│   │   │   ├── e2_agent_paramdef.h
│   │   │   ├── flexric
│   │   │   ├── RAN_FUNCTION
│   │   │   └── README.md
│   │   ├── ENB_APP
│   │   │   ├── enb_app.c
│   │   │   ├── enb_app.h
│   │   │   ├── enb_config.c
│   │   │   ├── enb_config_eMTC.c
│   │   │   ├── enb_config.h
│   │   │   ├── enb_config_SL.c
│   │   │   ├── enb_paramdef_emtc.h
│   │   │   ├── enb_paramdef.h
│   │   │   ├── enb_paramdef_mce.h
│   │   │   ├── enb_paramdef_mme.h
│   │   │   ├── enb_paramdef_sidelink.h
│   │   │   ├── L1_paramdef.h
│   │   │   ├── MACRLC_paramdef.h
│   │   │   ├── NB_IoT_interface.c
│   │   │   ├── NB_IoT_interface.h
│   │   │   ├── RRC_config_tools.c
│   │   │   ├── RRC_config_tools.h
│   │   │   └── RRC_paramsvalues.h
│   │   ├── F1AP
│   │   │   ├── CMakeLists.txt
│   │   │   ├── f1ap_common.c
│   │   │   ├── f1ap_common.h
│   │   │   ├── f1ap_cu_interface_management.c
│   │   │   ├── f1ap_cu_interface_management.h
│   │   │   ├── f1ap_cu_paging.c
│   │   │   ├── f1ap_cu_paging.h
│   │   │   ├── f1ap_cu_rrc_message_transfer.c
│   │   │   ├── f1ap_cu_rrc_message_transfer.h
│   │   │   ├── f1ap_cu_task.c
│   │   │   ├── f1ap_cu_task.h
│   │   │   ├── f1ap_cu_ue_context_management.c
│   │   │   ├── f1ap_cu_ue_context_management.h
│   │   │   ├── f1ap_default_values.h
│   │   │   ├── f1ap_du_interface_management.c
│   │   │   ├── f1ap_du_interface_management.h
│   │   │   ├── f1ap_du_paging.c
│   │   │   ├── f1ap_du_paging.h
│   │   │   ├── f1ap_du_rrc_message_transfer.c
│   │   │   ├── f1ap_du_rrc_message_transfer.h
│   │   │   ├── f1ap_du_task.c
│   │   │   ├── f1ap_du_task.h
│   │   │   ├── f1ap_du_ue_context_management.c
│   │   │   ├── f1ap_du_ue_context_management.h
│   │   │   ├── f1ap_encoder.c
│   │   │   ├── f1ap_encoder.h
│   │   │   ├── f1ap_handlers.c
│   │   │   ├── f1ap_ids.c
│   │   │   ├── f1ap_ids.h
│   │   │   ├── f1ap_ids_test.c
│   │   │   ├── f1ap_itti_messaging.c
│   │   │   ├── f1ap_itti_messaging.h
│   │   │   ├── lib
│   │   │   ├── MESSAGES
│   │   │   └── tests
│   │   ├── GNB_APP
│   │   │   ├── gnb_app.c
│   │   │   ├── gnb_app.h
│   │   │   ├── gnb_config.c
│   │   │   ├── gnb_config_common.c
│   │   │   ├── gnb_config_common.h
│   │   │   ├── gnb_config.h
│   │   │   ├── gnb_config_ng.c
│   │   │   ├── gnb_config_ng.h
│   │   │   ├── gnb_paramdef.h
│   │   │   ├── L1_nr_paramdef.h
│   │   │   ├── MACRLC_nr_paramdef.h
│   │   │   └── RRC_nr_paramsvalues.h
│   │   ├── LAYER2
│   │   │   ├── CMakeLists.txt
│   │   │   ├── MAC
│   │   │   ├── NR_MAC_COMMON
│   │   │   ├── NR_MAC_gNB
│   │   │   ├── NR_MAC_UE
│   │   │   ├── nr_pdcp
│   │   │   ├── nr_rlc
│   │   │   ├── openair2_proc.c
│   │   │   ├── PDCP_v10.1.0
│   │   │   ├── RLC
│   │   │   └── rlc_v2
│   │   ├── M2AP
│   │   │   ├── CMakeLists.txt
│   │   │   ├── m2ap_common.c
│   │   │   ├── m2ap_common.h
│   │   │   ├── m2ap_decoder.c
│   │   │   ├── m2ap_decoder.h
│   │   │   ├── m2ap_default_values.h
│   │   │   ├── m2ap_eNB.c
│   │   │   ├── m2ap_eNB_defs.h
│   │   │   ├── m2ap_eNB_generate_messages.c
│   │   │   ├── m2ap_eNB_generate_messages.h
│   │   │   ├── m2ap_eNB.h
│   │   │   ├── m2ap_eNB_handler.c
│   │   │   ├── m2ap_eNB_handler.h
│   │   │   ├── m2ap_eNB_interface_management.c
│   │   │   ├── m2ap_eNB_interface_management.h
│   │   │   ├── m2ap_eNB_management_procedures.c
│   │   │   ├── m2ap_eNB_management_procedures.h
│   │   │   ├── m2ap_encoder.c
│   │   │   ├── m2ap_encoder.h
│   │   │   ├── m2ap_handler.c
│   │   │   ├── m2ap_handler.h
│   │   │   ├── m2ap_ids.c
│   │   │   ├── m2ap_ids.h
│   │   │   ├── m2ap_itti_messaging.c
│   │   │   ├── m2ap_itti_messaging.h
│   │   │   ├── m2ap_MCE.c
│   │   │   ├── m2ap_MCE_defs.h
│   │   │   ├── m2ap_MCE_generate_messages.c
│   │   │   ├── m2ap_MCE_generate_messages.h
│   │   │   ├── m2ap_MCE.h
│   │   │   ├── m2ap_MCE_handler.c
│   │   │   ├── m2ap_MCE_handler.h
│   │   │   ├── m2ap_MCE_interface_management.c
│   │   │   ├── m2ap_MCE_interface_management.h
│   │   │   ├── m2ap_MCE_management_procedures.c
│   │   │   ├── m2ap_MCE_management_procedures.h
│   │   │   ├── m2ap_timers.c
│   │   │   ├── m2ap_timers.h
│   │   │   └── MESSAGES
│   │   ├── MCE_APP
│   │   │   ├── mce_app.c
│   │   │   ├── mce_app.h
│   │   │   ├── mce_config.c
│   │   │   └── mce_config.h
│   │   ├── NR_PHY_INTERFACE
│   │   │   ├── NR_IF_Module.c
│   │   │   └── NR_IF_Module.h
│   │   ├── NR_UE_PHY_INTERFACE
│   │   │   ├── NR_IF_Module.c
│   │   │   ├── NR_IF_Module.h
│   │   │   ├── NR_Packet_Drop.c
│   │   │   └── NR_Packet_Drop.h
│   │   ├── PHY_INTERFACE
│   │   │   ├── IF_Module.c
│   │   │   ├── IF_Module.h
│   │   │   ├── IF_Module_NB_IoT.h
│   │   │   ├── phy_interface_extern.h
│   │   │   ├── phy_interface.h
│   │   │   ├── phy_interface_vars.h
│   │   │   ├── phy_stub_UE.c
│   │   │   ├── phy_stub_UE.h
│   │   │   ├── queue_t.c
│   │   │   ├── queue_test.c
│   │   │   ├── queue_test_run
│   │   │   └── queue_t.h
│   │   ├── RRC
│   │   │   ├── CMakeLists.txt
│   │   │   ├── common.h
│   │   │   ├── L2_INTERFACE
│   │   │   ├── LTE
│   │   │   ├── NR
│   │   │   └── NR_UE
│   │   ├── SDAP
│   │   │   └── nr_sdap
│   │   ├── UTIL
│   │   │   ├── CLI
│   │   │   ├── CMakeLists.txt
│   │   │   ├── MATH
│   │   │   ├── OMG
│   │   │   ├── OMV
│   │   │   ├── OPT
│   │   │   └── OTG
│   │   ├── X2AP
│   │   │   ├── CMakeLists.txt
│   │   │   ├── MESSAGES
│   │   │   ├── x2ap_common.c
│   │   │   ├── x2ap_common.h
│   │   │   ├── x2ap_eNB.c
│   │   │   ├── x2ap_eNB_decoder.c
│   │   │   ├── x2ap_eNB_decoder.h
│   │   │   ├── x2ap_eNB_defs.h
│   │   │   ├── x2ap_eNB_encoder.c
│   │   │   ├── x2ap_eNB_encoder.h
│   │   │   ├── x2ap_eNB_generate_messages.c
│   │   │   ├── x2ap_eNB_generate_messages.h
│   │   │   ├── x2ap_eNB.h
│   │   │   ├── x2ap_eNB_handler.c
│   │   │   ├── x2ap_eNB_handler.h
│   │   │   ├── x2ap_eNB_itti_messaging.c
│   │   │   ├── x2ap_eNB_itti_messaging.h
│   │   │   ├── x2ap_eNB_management_procedures.c
│   │   │   ├── x2ap_eNB_management_procedures.h
│   │   │   ├── x2ap_ids.c
│   │   │   ├── x2ap_ids.h
│   │   │   ├── x2ap_timers.c
│   │   │   └── x2ap_timers.h
│   │   └── XNAP
│   │       ├── CMakeLists.txt
│   │       ├── lib
│   │       ├── MESSAGES
│   │       ├── tests
│   │       ├── xnap_common.c
│   │       └── xnap_common.h
│   ├── openair3
│   │   ├── CMakeLists.txt
│   │   ├── COMMON
│   │   │   ├── common_types.h
│   │   │   ├── intertask_interface_conf.h
│   │   │   └── security_types.h
│   │   ├── DOCS
│   │   │   ├── Latex
│   │   │   └── Makefile.am
│   │   ├── LPP
│   │   │   ├── CMakeLists.txt
│   │   │   └── MESSAGES
│   │   ├── M3AP
│   │   │   ├── CMakeLists.txt
│   │   │   ├── m3ap_common.c
│   │   │   ├── m3ap_common.h
│   │   │   ├── m3ap_decoder.c
│   │   │   ├── m3ap_decoder.h
│   │   │   ├── m3ap_default_values.h
│   │   │   ├── m3ap_encoder.c
│   │   │   ├── m3ap_encoder.h
│   │   │   ├── m3ap_handler.c
│   │   │   ├── m3ap_handler.h
│   │   │   ├── m3ap_ids.c
│   │   │   ├── m3ap_ids.h
│   │   │   ├── m3ap_itti_messaging.c
│   │   │   ├── m3ap_itti_messaging.h
│   │   │   ├── m3ap_MCE.c
│   │   │   ├── m3ap_MCE_defs.h
│   │   │   ├── m3ap_MCE_generate_messages.h
│   │   │   ├── m3ap_MCE_generate_messsages.c
│   │   │   ├── m3ap_MCE.h
│   │   │   ├── m3ap_MCE_handler.c
│   │   │   ├── m3ap_MCE_handler.h
│   │   │   ├── m3ap_MCE_interface_management.c
│   │   │   ├── m3ap_MCE_interface_management.h
│   │   │   ├── m3ap_MCE_management_procedures.c
│   │   │   ├── m3ap_MCE_management_procedures.h
│   │   │   ├── m3ap_MME.c
│   │   │   ├── m3ap_MME_defs.h
│   │   │   ├── m3ap_MME_generate_messages.c
│   │   │   ├── m3ap_MME_generate_messages.h
│   │   │   ├── m3ap_MME.h
│   │   │   ├── m3ap_MME_handler.c
│   │   │   ├── m3ap_MME_handler.h
│   │   │   ├── m3ap_MME_interface_management.c
│   │   │   ├── m3ap_MME_interface_management.h
│   │   │   ├── m3ap_MME_management_procedures.c
│   │   │   ├── m3ap_MME_management_procedures.h
│   │   │   ├── m3ap_timers.c
│   │   │   ├── m3ap_timers.h
│   │   │   └── MESSAGES
│   │   ├── MME_APP
│   │   │   ├── mme_app.c
│   │   │   ├── mme_app.h
│   │   │   ├── mme_config.c
│   │   │   └── mme_config.h
│   │   ├── NAS
│   │   │   ├── CMakeLists.txt
│   │   │   ├── COMMON
│   │   │   ├── NR_UE
│   │   │   ├── TEST
│   │   │   ├── TOOLS
│   │   │   └── UE
│   │   ├── NGAP
│   │   │   ├── CMakeLists.txt
│   │   │   ├── MESSAGES
│   │   │   ├── ngap_common.c
│   │   │   ├── ngap_common.h
│   │   │   ├── ngap_gNB.c
│   │   │   ├── ngap_gNB_context_management_procedures.c
│   │   │   ├── ngap_gNB_context_management_procedures.h
│   │   │   ├── ngap_gNB_decoder.c
│   │   │   ├── ngap_gNB_decoder.h
│   │   │   ├── ngap_gNB_default_values.h
│   │   │   ├── ngap_gNB_defs.h
│   │   │   ├── ngap_gNB_encoder.c
│   │   │   ├── ngap_gNB_encoder.h
│   │   │   ├── ngap_gNB.h
│   │   │   ├── ngap_gNB_handlers.c
│   │   │   ├── ngap_gNB_handlers.h
│   │   │   ├── ngap_gNB_itti_messaging.c
│   │   │   ├── ngap_gNB_itti_messaging.h
│   │   │   ├── ngap_gNB_management_procedures.c
│   │   │   ├── ngap_gNB_management_procedures.h
│   │   │   ├── ngap_gNB_mobility_management.c
│   │   │   ├── ngap_gNB_mobility_management.h
│   │   │   ├── ngap_gNB_nas_procedures.c
│   │   │   ├── ngap_gNB_nas_procedures.h
│   │   │   ├── ngap_gNB_nnsf.c
│   │   │   ├── ngap_gNB_nnsf.h
│   │   │   ├── ngap_gNB_NRPPa_transport_procedures.c
│   │   │   ├── ngap_gNB_NRPPa_transport_procedures.h
│   │   │   ├── ngap_gNB_overload.c
│   │   │   ├── ngap_gNB_overload.h
│   │   │   ├── ngap_gNB_paging.c
│   │   │   ├── ngap_gNB_paging.h
│   │   │   ├── ngap_gNB_pdu_session_management.c
│   │   │   ├── ngap_gNB_pdu_session_management.h
│   │   │   ├── ngap_gNB_ue_context.c
│   │   │   ├── ngap_gNB_ue_context.h
│   │   │   ├── ngap_msg_includes.h
│   │   │   ├── ngap_utils.h
│   │   │   └── tests
│   │   ├── NRPPA
│   │   │   ├── CMakeLists.txt
│   │   │   ├── MESSAGES
│   │   │   ├── nrppa_common.h
│   │   │   ├── nrppa_gNB.c
│   │   │   ├── nrppa_gNB_config.c
│   │   │   ├── nrppa_gNB_config.h
│   │   │   ├── nrppa_gNB_decoder.c
│   │   │   ├── nrppa_gNB_decoder.h
│   │   │   ├── nrppa_gNB_encoder.c
│   │   │   ├── nrppa_gNB_encoder.h
│   │   │   ├── nrppa_gNB.h
│   │   │   ├── nrppa_gNB_handlers.c
│   │   │   ├── nrppa_gNB_handlers.h
│   │   │   ├── nrppa_gNB_location_information_transfer.c
│   │   │   ├── nrppa_gNB_location_information_transfer.h
│   │   │   ├── nrppa_gNB_measurement_information_transfer.c
│   │   │   ├── nrppa_gNB_measurement_information_transfer.h
│   │   │   ├── nrppa_gNB_ue_context.c
│   │   │   ├── nrppa_gNB_ue_context.h
│   │   │   ├── nrppa_includes.h
│   │   │   └── test_nrppa.c
│   │   ├── ocp-gtpu
│   │   │   ├── CMakeLists.txt
│   │   │   ├── gtp_itf.cpp
│   │   │   ├── gtp_itf.h
│   │   │   ├── gtpu_extensions.c
│   │   │   ├── gtpu_extensions.h
│   │   │   └── tests
│   │   ├── S1AP
│   │   │   ├── CMakeLists.txt
│   │   │   ├── MESSAGES
│   │   │   ├── s1ap_common.h
│   │   │   ├── s1ap_eNB.c
│   │   │   ├── s1ap_eNB_context_management_procedures.c
│   │   │   ├── s1ap_eNB_context_management_procedures.h
│   │   │   ├── s1ap_eNB_decoder.c
│   │   │   ├── s1ap_eNB_decoder.h
│   │   │   ├── s1ap_eNB_default_values.h
│   │   │   ├── s1ap_eNB_defs.h
│   │   │   ├── s1ap_eNB_encoder.c
│   │   │   ├── s1ap_eNB_encoder.h
│   │   │   ├── s1ap_eNB.h
│   │   │   ├── s1ap_eNB_handlers.c
│   │   │   ├── s1ap_eNB_handlers.h
│   │   │   ├── s1ap_eNB_itti_messaging.c
│   │   │   ├── s1ap_eNB_itti_messaging.h
│   │   │   ├── s1ap_eNB_management_procedures.c
│   │   │   ├── s1ap_eNB_management_procedures.h
│   │   │   ├── s1ap_eNB_nas_procedures.c
│   │   │   ├── s1ap_eNB_nas_procedures.h
│   │   │   ├── s1ap_eNB_nnsf.c
│   │   │   ├── s1ap_eNB_nnsf.h
│   │   │   ├── s1ap_eNB_overload.c
│   │   │   ├── s1ap_eNB_overload.h
│   │   │   ├── s1ap_eNB_trace.c
│   │   │   ├── s1ap_eNB_trace.h
│   │   │   ├── s1ap_eNB_ue_context.c
│   │   │   └── s1ap_eNB_ue_context.h
│   │   ├── SCTP
│   │   │   ├── sctp_common.c
│   │   │   ├── sctp_common.h
│   │   │   ├── sctp_default_values.h
│   │   │   ├── sctp_eNB_defs.h
│   │   │   ├── sctp_eNB_itti_messaging.c
│   │   │   ├── sctp_eNB_itti_messaging.h
│   │   │   ├── sctp_eNB_task.c
│   │   │   └── sctp_eNB_task.h
│   │   ├── SECU
│   │   │   ├── aes_128_cbc_cmac.c
│   │   │   ├── aes_128_cbc_cmac.h
│   │   │   ├── aes_128_ctr.c
│   │   │   ├── aes_128_ctr.h
│   │   │   ├── aes_128_ecb.c
│   │   │   ├── aes_128_ecb.h
│   │   │   ├── aes_128.h
│   │   │   ├── curve_25519.c
│   │   │   ├── curve_25519.h
│   │   │   ├── kdf.c
│   │   │   ├── kdf.h
│   │   │   ├── key_nas_deriver.c
│   │   │   ├── key_nas_deriver.h
│   │   │   ├── nas_stream_eea0.c
│   │   │   ├── nas_stream_eea0.h
│   │   │   ├── nas_stream_eea1.c
│   │   │   ├── nas_stream_eea1.h
│   │   │   ├── nas_stream_eea2.c
│   │   │   ├── nas_stream_eea2.h
│   │   │   ├── nas_stream_eia1.c
│   │   │   ├── nas_stream_eia1.h
│   │   │   ├── nas_stream_eia2.c
│   │   │   ├── nas_stream_eia2.h
│   │   │   ├── rijndael.c
│   │   │   ├── rijndael.h
│   │   │   ├── secu_defs.c
│   │   │   ├── secu_defs.h
│   │   │   ├── sha_256_hmac.c
│   │   │   ├── sha_256_hmac.h
│   │   │   ├── snow3g.c
│   │   │   ├── snow3g.h
│   │   │   ├── x963_kdf.c
│   │   │   └── x963_kdf.h
│   │   ├── TEST
│   │   │   ├── Makefile.am
│   │   │   ├── test_aes128_cmac_encrypt.c
│   │   │   ├── test_aes128_ctr.c
│   │   │   ├── test_kdf.c
│   │   │   ├── test_s1ap.c
│   │   │   ├── test_secu.c
│   │   │   ├── test_secu_kenb.c
│   │   │   ├── test_secu_knas.c
│   │   │   ├── test_secu_knas_encrypt_eea1.c
│   │   │   ├── test_secu_knas_encrypt_eea2.c
│   │   │   ├── test_secu_knas_encrypt_eia1.c
│   │   │   ├── test_secu_knas_encrypt_eia2.c
│   │   │   └── test_secu_knas_stream_int.c
│   │   ├── UICC
│   │   │   ├── CMakeLists.txt
│   │   │   ├── pdu_session.c
│   │   │   ├── pdu_session.h
│   │   │   ├── usim_interface.c
│   │   │   └── usim_interface.h
│   │   └── UTILS
│   │       └── conversions.h
│   ├── openshift
│   │   ├── oai-clang-bc.yaml
│   │   ├── oai-clang-is.yaml
│   │   ├── oai-enb-bc.yaml
│   │   ├── oai-enb-is.yaml
│   │   ├── oai-gnb-aw2s-bc.yaml
│   │   ├── oai-gnb-aw2s-is.yaml
│   │   ├── oai-gnb-bc.yaml
│   │   ├── oai-gnb-fhi72-bc.yaml
│   │   ├── oai-gnb-fhi72-is.yaml
│   │   ├── oai-gnb-is.yaml
│   │   ├── oai-lte-ue-bc.yaml
│   │   ├── oai-lte-ue-is.yaml
│   │   ├── oai-nr-cuup-bc.yaml
│   │   ├── oai-nr-cuup-is.yaml
│   │   ├── oai-nr-ue-bc.yaml
│   │   ├── oai-nr-ue-is.yaml
│   │   ├── oai-physim-bc.yaml
│   │   ├── oai-physim-is.yaml
│   │   ├── ran-base-bc.yaml
│   │   ├── ran-base-is.yaml
│   │   ├── ran-base-log-retrieval.yaml
│   │   ├── ran-build-bc.yaml
│   │   ├── ran-build-fhi72-bc.yaml
│   │   ├── ran-build-fhi72-is.yaml
│   │   ├── ran-build-is.yaml
│   │   └── README.md
│   ├── pre-commit-clang
│   ├── radio
│   │   ├── AW2SORI
│   │   │   ├── CMakeLists.txt
│   │   │   ├── oaiori.c
│   │   │   └── ori.h
│   │   ├── BLADERF
│   │   │   ├── bladerf_lib.c
│   │   │   ├── CMakeLists.txt
│   │   │   └── README.md
│   │   ├── CMakeLists.txt
│   │   ├── COMMON
│   │   │   ├── CMakeLists.txt
│   │   │   ├── common_lib.c
│   │   │   ├── common_lib.h
│   │   │   ├── record_player.c
│   │   │   └── record_player.h
│   │   ├── emulator
│   │   │   ├── CMakeLists.txt
│   │   │   ├── README.md
│   │   │   └── rf_emulator.c
│   │   ├── ETHERNET
│   │   │   ├── CMakeLists.txt
│   │   │   ├── ethernet_lib.c
│   │   │   ├── ethernet_lib.h
│   │   │   ├── ethernet.md
│   │   │   ├── eth_raw.c
│   │   │   ├── eth_udp.c
│   │   │   └── if_defs.h
│   │   ├── fhi_72
│   │   │   ├── armral_bfp_compression.c
│   │   │   ├── armral_bfp_compression.h
│   │   │   ├── CMakeLists.txt
│   │   │   ├── mplane
│   │   │   ├── oaioran.c
│   │   │   ├── oaioran.h
│   │   │   ├── oran-config.c
│   │   │   ├── oran-config.h
│   │   │   ├── oran.h
│   │   │   ├── oran-init.c
│   │   │   ├── oran-init.h
│   │   │   ├── oran_isolate.c
│   │   │   ├── oran_isolate.h
│   │   │   ├── oran-params.h
│   │   │   └── README.md
│   │   ├── iqplayer
│   │   │   ├── DOC
│   │   │   └── iqplayer_lib.c
│   │   ├── IRIS
│   │   │   ├── CMakeLists.txt
│   │   │   └── iris_lib.cpp
│   │   ├── LMSSDR
│   │   │   ├── CMakeLists.txt
│   │   │   ├── LimeSDR_above_1p8GHz_1v4.ini
│   │   │   ├── LimeSDR_above_1p8GHz.ini
│   │   │   ├── LimeSDR_below_1p8GHz_1v4.ini
│   │   │   ├── LimeSDR_below_1p8GHz.ini
│   │   │   ├── LimeSDR.ini
│   │   │   ├── lms_lib.cpp
│   │   │   └── sodera_lib.cpp
│   │   ├── rfsimulator
│   │   │   ├── apply_channelmod.c
│   │   │   ├── CMakeLists.txt
│   │   │   ├── README.md
│   │   │   ├── rfsimulator.h
│   │   │   ├── simulator.cpp
│   │   │   └── stored_node.c
│   │   ├── USRP
│   │   │   ├── CMakeLists.txt
│   │   │   ├── README.md
│   │   │   └── usrp_lib.cpp
│   │   ├── vrtsim
│   │   │   ├── cirdb_provider.c
│   │   │   ├── cirdb_provider.h
│   │   │   ├── cirdb_yaml.cpp
│   │   │   ├── cirdb_yaml.h
│   │   │   ├── CMakeLists.txt
│   │   │   ├── README.md
│   │   │   ├── taps_client.cpp
│   │   │   ├── taps_client.h
│   │   │   ├── tests
│   │   │   └── vrtsim.c
│   │   └── zmq
│   │       ├── CMakeLists.txt
│   │       ├── README.md
│   │       ├── ring_buffer.cpp
│   │       ├── ring_buffer.h
│   │       ├── tests
│   │       ├── zmq_imported.cpp
│   │       ├── zmq_imported.h
│   │       └── zmq_radio.cpp
│   ├── rbconfig.raw
│   ├── README.md
│   ├── reconfig.raw
│   ├── targets
│   │   ├── DOCS
│   │   │   ├── E-UTRAN_User_Guide.docx
│   │   │   ├── E-UTRAN_User_Guide.pdf
│   │   │   ├── nfapi-L2-emulator-setup.txt
│   │   │   ├── oai_L1_L2_procedures.ipe
│   │   │   └── oai_L1_L2_procedures.pdf
│   │   ├── gtkwave
│   │   │   ├── eNB_usrp.gtkw
│   │   │   ├── gNB_usrp.gtkw
│   │   │   ├── pnf.gtkw
│   │   │   ├── rau_if4_single_thread.gtkw
│   │   │   ├── rcc_if4.gtkw
│   │   │   ├── rcc_if5.gtkw
│   │   │   ├── rru_if4p5_simulator.gtkw
│   │   │   ├── rru_if4p5_single_thread.gtkw
│   │   │   ├── rru_if4p5_usrp.gtkw
│   │   │   ├── rru_if5_usrp.gtkw
│   │   │   └── ue_usrp.gtkw
│   │   ├── PROJECTS
│   │   │   ├── CENTOS-LTE-EPC-INTEGRATION
│   │   │   ├── GENERIC-LTE-EPC
│   │   │   ├── GENERIC-NR-5GC
│   │   │   └── NR-SIDELINK
│   │   └── TEST
│   │       ├── AT_COMMANDS
│   │       ├── PDCP
│   │       └── ROHDE_SCHWARZ
│   ├── tests
│   │   ├── CMakeLists.txt
│   │   ├── nr-cu-nrppa
│   │   │   ├── CMakeLists.txt
│   │   │   ├── nr-cu-nrppa.c
│   │   │   ├── nr-nrppa-test.conf
│   │   │   └── README.md
│   │   ├── nr-cuup
│   │   │   ├── CMakeLists.txt
│   │   │   ├── load-test.conf
│   │   │   ├── nr-cuup-functional-test.sh
│   │   │   ├── nr-cuup-load-test.c
│   │   │   └── README.md
│   │   └── nr-ue-nas-simulator
│   │       ├── CMakeLists.txt
│   │       ├── nr-ue-nas-simulator.c
│   │       ├── README.md
│   │       └── test.conf
│   └── tools
│       ├── cppcheck
│       │   ├── docker-compose.yaml
│       │   ├── README.md
│       │   ├── run-cppcheck.sh
│       │   └── suppressions.list
│       ├── docker-dev-env
│       │   ├── bootstrap.sh
│       │   ├── docker-compose.yml
│       │   ├── Dockerfile
│       │   └── README.md
│       ├── formatting
│       │   ├── detect_clang_format_errors.sh
│       │   ├── docker-compose.yaml
│       │   └── README.md
│       ├── iwyu
│       │   ├── docker-compose.yaml
│       │   └── README.md
│       ├── packages
│       │   ├── packages.cmake
│       │   ├── systemd_scripts
│       │   ├── systemd_services
│       │   └── triggers
│       ├── plots
│       │   ├── ber_compare.svg
│       │   ├── dl_graph.py
│       │   ├── example.png
│       │   ├── plot-power-control.gp.sh
│       │   ├── README.md
│       │   ├── requirements.txt
│       │   └── ul_bler_vs_snr_graph.py
│       └── scripts
│           └── multi-ue.sh
├── ps-result.log
├── qos-flow-architecture.md
├── README.md
├── scheduler
│   └── __pycache__
│       ├── flow.cpython-312.pyc
│       ├── __init__.cpython-312.pyc
│       ├── interfaces.cpython-312.pyc
│       ├── link.cpython-312.pyc
│       ├── tier1.cpython-312.pyc
│       └── two_tier.cpython-312.pyc
├── script-logs
├── sensor_pf+twotier.png
├── sim
│   ├── baselines
│   │   └── __pycache__
│   │       ├── gradient.cpython-312.pyc
│   │       ├── __init__.cpython-312.pyc
│   │       ├── _mac.cpython-312.pyc
│   │       ├── pf.cpython-312.pyc
│   │       └── round_robin.cpython-312.pyc
│   ├── __pycache__
│   │   ├── buffer.cpython-312.pyc
│   │   ├── channel.cpython-312.pyc
│   │   ├── config.cpython-312.pyc
│   │   ├── config_loader.cpython-312.pyc
│   │   ├── driver.cpython-312.pyc
│   │   ├── __init__.cpython-312.pyc
│   │   ├── metrics.cpython-312.pyc
│   │   ├── resource.cpython-312.pyc
│   │   └── traffic.cpython-312.pyc
│   ├── scenarios
│   │   └── __pycache__
│   │       └── __init__.cpython-312.pyc
│   └── tests
│       └── __pycache__
│           ├── __init__.cpython-312.pyc
│           ├── test_config_loader.cpython-312-pytest-9.0.3.pyc
│           ├── test_driver.cpython-312-pytest-9.0.3.pyc
│           ├── test_interfaces.cpython-312-pytest-9.0.3.pyc
│           ├── test_link.cpython-312-pytest-7.4.4.pyc
│           ├── test_link.cpython-312-pytest-9.0.3.pyc
│           ├── test_smoke.cpython-312-pytest-9.0.3.pyc
│           ├── test_smoke_harq.cpython-312-pytest-9.0.3.pyc
│           └── test_two_tier_refactor.cpython-312-pytest-9.0.3.pyc
├── smoke_twotier.png
└── ue.log

366 directories, 1315 files
